"""Ordered, streaming Step pipeline Job."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator, Mapping, Sequence
from contextlib import aclosing
from copy import deepcopy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ....client.events import JobEvent, ResultEvent
from ...config.models import ComponentConfig
from ...registry import provider
from ...steps.base import BaseStep
from ..component_type import ComponentType
from .base import BaseJob
from .context import RuntimeContext

if TYPE_CHECKING:
    from ...core.context import ApplicationContext


@dataclass(frozen=True, slots=True)
class StepPlan:
    """Resolved Step implementation and options copied for each invocation."""

    step_class: type[BaseStep]
    options: dict[str, Any]


@provider("pipeline")
class PipelineJob(BaseJob):
    """Run fresh asynchronous Steps sequentially as one event stream."""

    def __init__(
        self,
        *,
        app_context: ApplicationContext,
        steps: Sequence[ComponentConfig | Mapping[str, Any]] = (),
        defaults: Mapping[str, Any] | None = None,
        event_buffer_size: int = 64,
        **kwargs,
    ) -> None:
        if isinstance(event_buffer_size, bool) or not isinstance(event_buffer_size, int) or event_buffer_size < 1:
            raise ValueError("event_buffer_size must be a positive integer")
        self._defaults = dict(defaults or {})
        self._event_buffer_size = event_buffer_size
        self._active_steps: set[asyncio.Task[Any]] = set()
        self._accepting = False
        self._plans = tuple(self._resolve_plan(app_context, raw) for raw in steps)
        super().__init__(app_context=app_context, **kwargs)

    @staticmethod
    def _resolve_plan(
        app_context: ApplicationContext,
        raw: ComponentConfig | Mapping[str, Any],
    ) -> StepPlan:
        config = ComponentConfig.model_validate(raw)
        step_class = app_context.registry.require(ComponentType.STEP, config.backend, BaseStep)
        return StepPlan(step_class, config.model_dump())

    def _injected_parameters(self) -> Mapping[str, Any]:
        merged: dict[str, Any] = {}
        for plan in self._plans:
            for name, schema in plan.step_class.injected_parameters.items():
                if name in merged and merged[name] != schema:
                    raise ValueError(f"Conflicting injected Job parameter: {name!r}")
                merged[name] = schema
        return merged

    async def _start(self) -> None:
        self._accepting = True

    async def _close(self) -> None:
        self._accepting = False
        tasks = tuple(self._active_steps)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def _build_steps(self) -> Iterator[BaseStep]:
        for plan in self._plans:
            yield plan.step_class(app_context=self.app_context, **deepcopy(plan.options))

    @staticmethod
    async def _drain(
        events: asyncio.Queue[JobEvent],
        step_task: asyncio.Task[Any],
    ) -> AsyncIterator[JobEvent]:
        """Yield queued events until the Step finishes, without completion races."""
        while not step_task.done() or not events.empty():
            next_event = asyncio.create_task(events.get())
            try:
                done, _ = await asyncio.wait(
                    (step_task, next_event),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if next_event in done:
                    yield next_event.result()
            finally:
                next_event.cancel()
                await asyncio.gather(next_event, return_exceptions=True)
        await step_task

    # Async generators satisfy the base contract returning an AsyncIterator.
    async def stream(  # pylint: disable=invalid-overridden-method
        self,
        arguments: Mapping[str, Any],
        system: Mapping[str, Any],
    ) -> AsyncIterator[JobEvent]:
        if not self._accepting:
            raise RuntimeError(f"Job {self.name!r} is not running")

        context = RuntimeContext(self._defaults, arguments, system)
        try:
            for step in self._build_steps():
                events: asyncio.Queue[JobEvent] = asyncio.Queue(self._event_buffer_size)
                step_task = asyncio.create_task(
                    step(context, events.put),
                    name=f"axonx-job:{self.name}:{type(step).__name__}",
                )
                self._active_steps.add(step_task)
                try:
                    async with aclosing(self._drain(events, step_task)) as stream:
                        async for event in stream:
                            yield event
                finally:
                    if not step_task.done():
                        step_task.cancel()
                    await asyncio.gather(step_task, return_exceptions=True)
                    self._active_steps.discard(step_task)
                if not context.response.success:
                    break
        except Exception as exc:
            if isinstance(exc, ValueError):
                self.logger.warning(f"Job failed: {type(exc).__name__}: {exc}")
            else:
                self.logger.exception("Job failed")
            context.response.fail(exc)
        yield ResultEvent.from_response(context.response)
