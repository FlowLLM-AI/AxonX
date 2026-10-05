"""Small synchronous window primitives; the TaskRunner owns task lifecycle."""

from __future__ import annotations

import time
from abc import abstractmethod
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from ...utils.fs import atomic_write_json
from ..core import BaseInputParams, BaseTask
from ..storage.artifacts import artifact_record


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
    elapsed_seconds: float = Field(default=0, ge=0)
    rows: int = Field(default=0, ge=0)
    coverage: float | None = Field(default=None, ge=0, le=1)
    artifacts: dict[str, dict[str, Any]] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)


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


class WindowClock:
    """Override in tests; elapsed time and request budgets use a monotonic clock."""

    def now(self) -> datetime:
        return datetime.now(UTC)

    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


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
            self.write_manifest()
            for window in self.input_params.windows:
                started = self.clock.monotonic()
                try:
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
                        if result.status == "done" and budget.remaining_seconds <= 0:
                            result = result.model_copy(update={"status": "incomplete", "reason": "deadline_exceeded"})
                except Exception as exc:
                    self.window_results.append(
                        WindowResult(
                            key=window.key,
                            status="failed",
                            reason=f"{type(exc).__name__}: {exc}",
                            elapsed_seconds=self.clock.monotonic() - started,
                        )
                    )
                    self.write_manifest()
                    raise
                result.elapsed_seconds = self.clock.monotonic() - started
                self.window_results.append(result)
                self.write_manifest()
        except BaseException:
            try:
                self.close_run()
            except Exception:
                self.logger.exception("Resource cleanup failed after primary failure")
            raise
        else:
            self.close_run()

    def write_manifest(self) -> None:
        atomic_write_json(self.task_dir / "manifest.json", self.manifest_data())

    def manifest_data(self) -> dict:
        return {"windows": [result.model_dump(mode="json") for result in self.window_results]}

    def window_output(self) -> dict:
        path = self.task_dir / "manifest.json"
        return {
            "windows": self.window_results,
            "manifest_file": str(path),
            "artifacts": {"manifest": artifact_record(path, self.task_dir)},
        }
