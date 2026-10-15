"""Small synchronous window primitives; the TaskRunner owns task lifecycle."""

from __future__ import annotations

from abc import abstractmethod
from datetime import datetime
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from ..core import BaseInputParams, BaseTask
from ..clock import WindowClock


class ExecutionWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(min_length=1)
    start_at: AwareDatetime
    end_at: AwareDatetime

    @model_validator(mode="after")
    def validate_range(self):
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        return self


class WindowResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    status: Literal["done", "skipped", "incomplete", "failed"]
    reason: str = ""
    commit_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    committed_at: AwareDatetime | None = None
    elapsed_seconds: float = Field(default=0, ge=0)
    rows: int = Field(default=0, ge=0)
    coverage: float | None = Field(default=None, ge=0, le=1)
    artifacts: dict[str, dict[str, Any]] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_commit(self):
        if (self.commit_id is None) != (self.committed_at is None):
            raise ValueError("commit_id and committed_at must be supplied together")
        if self.commit_id is not None and self.status != "done":
            raise ValueError("Only completed windows may publish a commit")
        return self


class WindowInputParams(BaseInputParams):
    windows: list[ExecutionWindow] = Field(min_length=1)
    poll_interval_seconds: float = Field(default=1, gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_windows(self):
        keys = [window.key for window in self.windows]
        if len(keys) != len(set(keys)):
            raise ValueError("window keys must be unique")
        if self.windows != sorted(self.windows, key=lambda window: window.start_at):
            raise ValueError("windows must be ordered by start_at")
        return self


class DeadlineBudget:
    """Plugins must bound request timeouts, retries and backoff by remaining seconds."""

    def __init__(self, clock: WindowClock, end_at: datetime):
        self.clock = clock
        self.deadline = clock.monotonic() + max(0, (end_at - clock.now()).total_seconds())

    @property
    def remaining_seconds(self) -> float:
        return max(0, self.deadline - self.clock.monotonic())

    def sleep(self, seconds: float) -> None:
        self.clock.sleep(max(0, min(seconds, self.remaining_seconds)))

    def check(self) -> None:
        """Fail before beginning or publishing work after the deadline."""
        if self.remaining_seconds <= 0:
            raise TimeoutError("Window deadline exceeded")


class _WindowTask(BaseTask):
    """Shared orchestration only; no market calendar, model or data format assumptions."""

    input_cls = WindowInputParams
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
