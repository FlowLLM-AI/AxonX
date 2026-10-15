"""Online inference with fixed model identity and bounded input waiting."""

from abc import abstractmethod

from pydantic import TypeAdapter

from ...enums import TaskType
from ..core.clock import DeadlineBudget
from .windows import ExecutionWindow, WindowInputParams, WindowOutputParams, WindowResult, _WindowTask


class BaseInferenceOutputParams(WindowOutputParams):
    model_identity: dict[str, str]


class BaseInferenceTask(_WindowTask):
    model_identity: dict[str, str]
    _fixed_model_identity: dict[str, str]
    task_type = TaskType.INFERENCE
    input_cls = WindowInputParams
    output_cls = BaseInferenceOutputParams

    @abstractmethod
    def initialize_run(self) -> None:
        """Resolve model once and set model_identity (path, fingerprint and protocol)."""

    @abstractmethod
    def inputs_ready(self, window: ExecutionWindow) -> bool:
        """Check atomically published inputs; return False while waiting."""

    @abstractmethod
    def infer(self, window: ExecutionWindow, budget: DeadlineBudget) -> WindowResult:
        """Validate freshness/quality, then predict with the fixed model and normalization."""

    def execute_window(self, window: ExecutionWindow, budget: DeadlineBudget) -> WindowResult:
        if self.model_identity != self._fixed_model_identity:
            raise ValueError("Model identity changed within an inference run")
        while budget.remaining_seconds > 0:
            if self.inputs_ready(window):
                if budget.remaining_seconds <= 0:
                    break
                if self.model_identity != self._fixed_model_identity:
                    raise ValueError("Model identity changed within an inference run")
                result = self.infer(window, budget)
                if self.model_identity != self._fixed_model_identity:
                    raise ValueError("Model identity changed within an inference run")
                return result
            budget.sleep(self.input_params.poll_interval_seconds)
        return WindowResult(key=window.key, status="incomplete", reason="inputs_timeout")

    def validate_run(self) -> None:
        if not isinstance(getattr(self, "model_identity", None), dict) or not self.model_identity:
            raise ValueError("initialize_run must set a nonempty model_identity")
        self._fixed_model_identity = TypeAdapter(dict[str, str]).validate_python(self.model_identity)

    def window_output(self) -> dict:
        return {**super().window_output(), "model_identity": self._fixed_model_identity}
