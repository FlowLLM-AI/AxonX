"""Step-based jobs."""

import asyncio
from collections.abc import Iterator, Mapping, Sequence
from copy import deepcopy
from typing import Any

from ...context import RuntimeContext
from ...enums import ComponentEnum, JobMode
from ...schema import ComponentConfig, Response
from ...steps.base import BaseStep
from ..registry import R
from .base import BaseJob

_StepSpec = tuple[type[BaseStep], dict[str, Any]]


@R.register("simple")
class SimpleJob(BaseJob):
    """Run freshly constructed asynchronous steps once, in declaration order."""

    @property
    def mode(self) -> JobMode:
        """Run only when explicitly invoked."""
        return JobMode.ON_DEMAND

    def __init__(
        self,
        steps: Sequence[ComponentConfig | Mapping[str, Any]] = (),
        defaults: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._step_configs = tuple(steps)
        self._defaults = dict(defaults or {})
        self._step_specs: tuple[_StepSpec, ...] = ()
        self._active_tasks: set[asyncio.Task[Any]] = set()

    async def _start(self) -> None:
        self._step_specs = tuple(map(self._resolve_step, self._step_configs))

    async def _close(self) -> None:
        current_task = asyncio.current_task()
        active_tasks = [task for task in self._active_tasks if task is not current_task]
        for task in active_tasks:
            task.cancel()
        await asyncio.gather(*active_tasks, return_exceptions=True)
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

    async def __call__(self, **kwargs: Any) -> Response:
        task = asyncio.current_task()
        if task is not None:
            self._active_tasks.add(task)
        try:
            context = RuntimeContext(**deepcopy(self._defaults))
            context.update(kwargs)
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
        finally:
            if task is not None:
                self._active_tasks.discard(task)
