"""Sequential asynchronous jobs."""

from collections.abc import Iterator, Mapping, Sequence
from copy import deepcopy
from typing import Any

from jsonschema.validators import validator_for

from ...enumeration import ComponentEnum
from ...schema import ComponentConfig, JobInfo, Response
from ...steps.base_step import BaseStep
from ..base_component import BaseComponent
from ..component_registry import R
from ..runtime_context import RuntimeContext

_StepSpec = tuple[type[BaseStep], dict[str, Any]]


@R.register("base")
class BaseJob(BaseComponent):
    """Run freshly constructed asynchronous steps once, in declaration order."""

    component_type = ComponentEnum.JOB
    runs_in_background = False

    def __init__(
        self,
        description: str = "",
        parameters: Mapping[str, Any] | None = None,
        enable_serve: bool = True,
        steps: Sequence[ComponentConfig | Mapping[str, Any]] = (),
        defaults: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        if self.kwargs:
            options = ", ".join(sorted(self.kwargs))
            raise TypeError(f"Unsupported {type(self).__name__} options: {options}")
        self._step_configs = tuple(steps)
        self._defaults = dict(defaults or {})
        self.description = description
        self.parameters = deepcopy(
            parameters if parameters is not None else {"properties": {}},
        )
        self.parameters.setdefault("type", "object")
        validator_class = validator_for(self.parameters)
        validator_class.check_schema(self.parameters)
        self._parameter_validator = validator_class(self.parameters)
        self.enable_serve = enable_serve
        self._step_specs: tuple[_StepSpec, ...] = ()

    @property
    def is_servable(self) -> bool:
        """Whether remote services may expose this job."""
        return self.enable_serve and not self.runs_in_background

    @property
    def info(self) -> JobInfo:
        """Describe this job's public input and output schemas."""
        return JobInfo(
            name=self.name,
            description=self.description,
            inputSchema=deepcopy(self.parameters),
            outputSchema=Response.model_json_schema(),
        )

    def validate_arguments(self, arguments: Mapping[str, Any]) -> None:
        """Raise ``ValueError`` when arguments violate the job schema."""
        error = next(self._parameter_validator.iter_errors(arguments), None)
        if error is not None:
            location = ".".join(map(str, error.absolute_path))
            prefix = f"{location}: " if location else ""
            raise ValueError(
                f"Invalid arguments for job {self.name!r}: {prefix}{error.message}",
            )

    async def _start(self) -> None:
        self._step_specs = tuple(map(self._resolve_step, self._step_configs))

    async def _close(self) -> None:
        self._step_specs = ()

    def _resolve_step(self, raw: ComponentConfig | Mapping[str, Any]) -> _StepSpec:
        config = ComponentConfig.model_validate(raw)
        step_class = self.app_context.registry.get(ComponentEnum.STEP, config.backend)
        if step_class is None or not issubclass(step_class, BaseStep):
            raise ValueError(f"Unknown async step: {config.backend}")
        return step_class, config.model_dump()

    def _build_steps(self) -> Iterator[BaseStep]:
        for step_class, options in self._step_specs:
            yield step_class(app_context=self.app_context, **deepcopy(options))

    async def __call__(self, **arguments: Any) -> Response:
        context = RuntimeContext(**deepcopy(self._defaults))
        context.update(arguments)
        try:
            for step in self._build_steps():
                await step(context)
                if not context.response.success:
                    break
        except Exception as exc:
            self.logger.exception("Job failed")
            context.response.success = False
            context.response.answer = f"{type(exc).__name__}: {exc}"
        return context.response
