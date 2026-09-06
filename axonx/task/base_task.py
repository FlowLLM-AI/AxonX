"""Base types for synchronous tasks."""

from collections.abc import Callable, Iterable
from typing import Any, get_type_hints

from pydantic import BaseModel, ConfigDict

from ..enumeration import ComponentEnum
from ..utils import get_logger


class BaseConfig(BaseModel):
    """Forbid unknown task configuration fields by default."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class BaseTask:
    """Run lazily generated synchronous steps in a shared context."""

    component_type = ComponentEnum.TASK
    config_class = BaseConfig
    output_keys: tuple[str, ...] = ()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if "config" not in cls.__dict__.get("__annotations__", {}):
            return
        config_class = get_type_hints(cls)["config"]
        if not isinstance(config_class, type) or not issubclass(config_class, BaseConfig):
            raise TypeError("Task config must subclass BaseConfig")
        cls.config_class = config_class

    def __init__(self, config: BaseConfig | dict, **kwargs: Any):
        self.config = self.config_class.model_validate(config)
        self.context = dict(kwargs)
        self.logger = get_logger(type(self).__name__)

    def build_task_steps(self) -> Iterable[Callable[[], None]]:
        """Yield synchronous callables lazily in execution order."""
        raise NotImplementedError

    @property
    def output(self) -> dict[str, Any]:
        """Select declared output fields from the shared task context."""
        return {key: self.context[key] for key in self.output_keys}

    def execute(
        self,
        *,
        emit: Callable[..., None] = lambda **_: None,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> dict[str, Any]:
        """Execute lazy task steps, reporting progress between boundaries."""
        for index, step in enumerate(self.build_task_steps(), 1):
            if cancelled():
                raise RuntimeError("Task cancellation requested")
            name = getattr(step, "__name__", type(step).__name__)
            emit(step_index=index - 1, task_step={"name": name, "percentage": None})
            step()
            emit(step_index=index - 1, task_step={"name": name, "percentage": 100})
        if cancelled():
            raise RuntimeError("Task cancellation requested")
        return self.output

    def exit_code(self, _output: dict[str, Any]) -> int:
        """Return the worker exit code for a successful task output."""
        return 0
