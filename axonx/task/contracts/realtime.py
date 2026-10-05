"""Business-neutral realtime API collection contract."""

from abc import abstractmethod

from pydantic import Field

from ...enums import TaskType
from ..core import BaseOutputParams
from .windows import DeadlineBudget, ExecutionWindow, WindowInputParams, WindowResult, _WindowTask


class BaseRealtimeApiInputParams(WindowInputParams):
    pass


class BaseRealtimeApiOutputParams(BaseOutputParams):
    manifest_file: str
    windows: list[WindowResult] = Field(default_factory=list)


class BaseRealtimeApiTask(_WindowTask):
    task_type = TaskType.API
    input_cls = BaseRealtimeApiInputParams
    output_cls = BaseRealtimeApiOutputParams

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

    def build_output_params(self) -> BaseRealtimeApiOutputParams:
        return self.output_cls(**self.window_output())
