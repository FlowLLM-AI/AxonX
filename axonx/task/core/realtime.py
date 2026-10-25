"""Domain execution and shared operations."""

from __future__ import annotations

from abc import abstractmethod

from .clock import DeadlineBudget
from .windows import _WindowTask
from ..task_enums import TaskType
from ..models.windows import ExecutionWindow, WindowInputParams, WindowResult


class BaseRealtimeApiTask(_WindowTask):
    task_type = TaskType.API
    input_cls = WindowInputParams

    @abstractmethod
    def collect(self, window: ExecutionWindow, budget: DeadlineBudget) -> WindowResult | None:
        """Return a final outcome, or None to poll again. Publish final data only when complete."""

    def execute_window(self, window: ExecutionWindow, budget: DeadlineBudget) -> WindowResult:
        while budget.remaining_seconds > 0:
            result = self.collect(window, budget)
            if result is not None:
                return result
            budget.sleep(self.input_params.poll_interval_seconds)
        return WindowResult(key=window.key, status="incomplete", reason="deadline_exceeded")
