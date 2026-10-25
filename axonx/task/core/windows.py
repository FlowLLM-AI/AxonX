"""Domain execution and shared operations."""

from __future__ import annotations

from abc import abstractmethod

from .clock import DeadlineBudget, WindowClock
from .task import BaseTask
from ..models.windows import (
    ExecutionWindow,
    WindowInputParams,
    WindowOutputParams,
    WindowResult,
)


class _WindowTask(BaseTask):
    """Shared orchestration only; no market calendar, model or data format assumptions."""

    report_kind = "online"
    input_cls = WindowInputParams
    output_cls = WindowOutputParams
    window_results: list[WindowResult]
    clock: WindowClock

    def initialize_run(self) -> None:
        """Resolve fixed inputs and acquire owned resources once."""

    def validate_run(self) -> None:
        """Validate initialized protocol before any window executes."""

    def close_run(self) -> None:
        """Drain and close owned resources, including when initialization fails."""

    def window_skip_reason(self, _window: ExecutionWindow) -> str | None:
        """Return a business skip reason before waiting, or None to execute the window."""
        return None

    @abstractmethod
    def execute_window(self, window: ExecutionWindow, budget: DeadlineBudget) -> WindowResult:
        """Execute within the supplied budget; exceptions stop this task."""

    def build_task_steps(self):
        yield self.run_windows

    def run_windows(self) -> None:
        self.clock = getattr(self, "clock", WindowClock())
        self.window_results: list[WindowResult] = []
        try:
            self.initialize_run()
            self.validate_run()
            self.publish_windows()
            for window in self.input_params.windows:
                started = self.clock.monotonic()
                try:
                    if reason := self.window_skip_reason(window):
                        result = WindowResult(key=window.key, status="skipped", reason=reason)
                    else:
                        budget = DeadlineBudget(self.clock, window.end_at)
                        while self.clock.now() < window.start_at and budget.remaining_seconds > 0:
                            budget.sleep(
                                min(
                                    self.input_params.poll_interval_seconds,
                                    (window.start_at - self.clock.now()).total_seconds(),
                                )
                            )
                        if budget.remaining_seconds <= 0:
                            result = WindowResult(key=window.key, status="skipped", reason="window_missed")
                        else:
                            result = self.execute_window(window, budget)
                            if result.key != window.key:
                                raise ValueError("Window result key does not match the executing window")
                            if result.commit_id and (
                                result.status != "done"
                                or result.committed_at is None
                                or not window.start_at <= result.committed_at <= window.end_at
                            ):
                                raise ValueError("Invalid committed window result")
                            if result.status == "done" and not result.commit_id and budget.remaining_seconds <= 0:
                                result = result.model_copy(
                                    update={
                                        "status": "incomplete",
                                        "reason": "deadline_exceeded",
                                    }
                                )
                except Exception as exc:
                    self.window_results.append(
                        WindowResult(
                            key=window.key,
                            status="failed",
                            reason=f"{type(exc).__name__}: {exc}",
                            elapsed_seconds=self.clock.monotonic() - started,
                        )
                    )
                    self.publish_windows()
                    raise
                result.elapsed_seconds = self.clock.monotonic() - started
                self.window_results.append(result)
                self.publish_windows()
        except BaseException:
            try:
                self.close_run()
            except Exception:
                self.logger.exception("Resource cleanup failed after primary failure")
            raise
        else:
            self.close_run()

    def publish_windows(self) -> None:
        self.metadata.output_params.update(self.window_output())
        self.persist_metadata()

    def window_output(self) -> dict:
        return {"windows": [result.model_dump(mode="json") for result in self.window_results]}

    def build_output_params(self) -> WindowOutputParams:
        return self.output_cls(**self.window_output())
