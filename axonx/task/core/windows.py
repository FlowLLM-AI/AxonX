"""Window scheduling, realtime collection and fixed-model inference Tasks."""

from __future__ import annotations

from abc import abstractmethod
from datetime import UTC

from pydantic import TypeAdapter

from ..models.identity import TaskType
from ..models.params import (
    BaseInferenceOutputParams,
    ExecutionWindow,
    WindowInputParams,
    WindowOutputParams,
)
from ..models.reports import WindowResult
from .base import BaseTask
from .clock import DeadlineBudget


class BaseWindowTask(BaseTask):
    """Run ordered windows and publish each outcome; the executor owns cleanup via close()."""

    report_kind = "online"
    input_cls = WindowInputParams
    output_cls = WindowOutputParams
    window_results: list[WindowResult]

    def initialize_run(self) -> None:
        """Resolve fixed inputs and acquire owned resources once."""

    def validate_run(self) -> None:
        """Validate initialized protocol before any window executes."""

    def window_skip_reason(self, _window: ExecutionWindow) -> str | None:
        """Return a business skip reason before waiting, or None to execute."""
        return None

    @abstractmethod
    def execute_window(self, window: ExecutionWindow, budget: DeadlineBudget) -> WindowResult:
        """Execute within the supplied budget; exceptions stop this Task."""

    def build_task_steps(self):
        yield self.run_windows

    def run_windows(self) -> None:
        self.window_results = []
        self.initialize_run()
        self.validate_run()
        self.publish_output()
        for window in self.input_params.windows:
            started = self.clock.monotonic()
            try:
                result = self._run_window(window)
            except Exception as exc:
                self._record_window(
                    WindowResult(key=window.key, status="failed", reason=f"{type(exc).__name__}: {exc}"),
                    started,
                )
                raise
            self._record_window(result, started)

    def _run_window(self, window: ExecutionWindow) -> WindowResult:
        if reason := self.window_skip_reason(window):
            return WindowResult(key=window.key, status="skipped", reason=reason)
        budget = DeadlineBudget(self.clock, window.end_at)
        start_at = window.start_at.astimezone(UTC)
        while self.clock.now() < start_at and budget.remaining_seconds > 0:
            budget.sleep(min(self.input_params.poll_interval_seconds, (start_at - self.clock.now()).total_seconds()))
        if budget.remaining_seconds <= 0:
            return WindowResult(key=window.key, status="skipped", reason="window_missed")
        result = self.execute_window(window, budget)
        if result.key != window.key:
            raise ValueError("Window result key does not match the executing window")
        if result.commit_id and (
            result.status != "done"
            or result.committed_at is None
            or not start_at <= result.committed_at.astimezone(UTC) <= window.end_at.astimezone(UTC)
        ):
            raise ValueError("Invalid committed window result")
        if result.status == "done" and not result.commit_id and budget.remaining_seconds <= 0:
            return result.model_copy(update={"status": "incomplete", "reason": "deadline_exceeded"})
        return result

    def _record_window(self, result: WindowResult, started: float) -> None:
        result.elapsed_seconds = self.clock.monotonic() - started
        self.window_results.append(result)
        self.publish_output()

    def build_output_params(self) -> WindowOutputParams:
        return self.output_cls(windows=self.window_results)


class BaseRealtimeApiTask(BaseWindowTask):
    """Poll a collector within each window until it returns a final result."""

    task_type = TaskType.API

    @abstractmethod
    def collect(self, window: ExecutionWindow, budget: DeadlineBudget) -> WindowResult | None:
        """Return a final outcome, or None to poll again; publish only complete data."""

    def execute_window(self, window: ExecutionWindow, budget: DeadlineBudget) -> WindowResult:
        while budget.remaining_seconds > 0:
            result = self.collect(window, budget)
            if result is not None:
                return result
            budget.sleep(self.input_params.poll_interval_seconds)
        return WindowResult(key=window.key, status="incomplete", reason="deadline_exceeded")


class BaseInferenceTask(BaseWindowTask):
    """Wait for inputs and infer with one validated model identity for the whole run."""

    task_type = TaskType.INFERENCE
    output_cls = BaseInferenceOutputParams
    model_identity: dict[str, str]
    _fixed_model_identity: dict[str, str]

    @abstractmethod
    def initialize_run(self) -> None:
        """Resolve the model once and set a nonempty model_identity mapping."""

    @abstractmethod
    def inputs_ready(self, window: ExecutionWindow) -> bool:
        """Check atomically published inputs; return False while waiting."""

    @abstractmethod
    def infer(self, window: ExecutionWindow, budget: DeadlineBudget) -> WindowResult:
        """Validate freshness and quality, then predict with the fixed model."""

    def validate_run(self) -> None:
        if not isinstance(getattr(self, "model_identity", None), dict) or not self.model_identity:
            raise ValueError("initialize_run must set a nonempty model_identity")
        self._fixed_model_identity = TypeAdapter(dict[str, str]).validate_python(self.model_identity)

    def _check_model_identity(self) -> None:
        if self.model_identity != self._fixed_model_identity:
            raise ValueError("Model identity changed within an inference run")

    def execute_window(self, window: ExecutionWindow, budget: DeadlineBudget) -> WindowResult:
        self._check_model_identity()
        while budget.remaining_seconds > 0:
            ready = self.inputs_ready(window)
            self._check_model_identity()
            if ready:
                if budget.remaining_seconds <= 0:
                    break
                result = self.infer(window, budget)
                self._check_model_identity()
                return result
            budget.sleep(self.input_params.poll_interval_seconds)
        return WindowResult(key=window.key, status="incomplete", reason="inputs_timeout")

    def build_output_params(self) -> BaseInferenceOutputParams:
        return self.output_cls(windows=self.window_results, model_identity=self._fixed_model_identity)
