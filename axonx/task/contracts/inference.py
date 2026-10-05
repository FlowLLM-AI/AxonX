"""Online inference with fixed model identity and bounded input waiting."""

from abc import abstractmethod

from pydantic import Field, TypeAdapter

from ...enums import TaskType
from ..core import BaseOutputParams
from .windows import DeadlineBudget, ExecutionWindow, WindowInputParams, WindowResult, _WindowTask


class BaseInferenceInputParams(WindowInputParams):
    pass


class BaseInferenceOutputParams(BaseOutputParams):
    manifest_file: str
    model_identity: dict[str, str]
    windows: list[WindowResult] = Field(default_factory=list)


class BaseInferenceTask(_WindowTask):
    model_identity: dict[str, str]
    _fixed_model_identity: dict[str, str]
    task_type = TaskType.INFERENCE
    input_cls = BaseInferenceInputParams
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
        while budget.remaining_seconds > 0:
            if self.inputs_ready(window):
                if budget.remaining_seconds <= 0:
                    break
                return self.infer(window, budget)
            budget.sleep(self.input_params.poll_interval_seconds)
        return WindowResult(key=window.key, status="incomplete", reason="inputs_timeout")

    def validate_run(self) -> None:
        if not isinstance(getattr(self, "model_identity", None), dict) or not self.model_identity:
            raise ValueError("initialize_run must set a nonempty model_identity")
        self._fixed_model_identity = TypeAdapter(dict[str, str]).validate_python(self.model_identity)

    def manifest_data(self) -> dict:
        return {**super().manifest_data(), "model_identity": self._fixed_model_identity}

    def build_output_params(self) -> BaseInferenceOutputParams:
        return self.output_cls(model_identity=self._fixed_model_identity, **self.window_output())
