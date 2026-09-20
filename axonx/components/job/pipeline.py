"""Ordered, streaming Step pipeline Job."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from ...config import ComponentConfig
from ...core.context import ApplicationContext
from ...enums import ComponentEnum
from ...steps.base import BaseStep
from ..registry import provider
from .base import BaseJob, JobEvent, ResultEvent
from .context import RuntimeContext


@dataclass(frozen=True, slots=True)
class StepPlan:
    """Resolved Step implementation and immutable construction options."""

    step_class: type[BaseStep]
    options: dict[str, Any]


@provider("pipeline")
class PipelineJob(BaseJob):
    """Run fresh asynchronous Steps sequentially as one event stream."""

    def __init__(
        self,
        steps: Sequence[ComponentConfig | Mapping[str, Any]] = (),
        defaults: Mapping[str, Any] | None = None,
        event_buffer_size: int = 64,
        app_context: ApplicationContext | None = None,
        **kwargs,
    ) -> None:
        if not isinstance(event_buffer_size, int) or event_buffer_size < 1:
            raise ValueError("event_buffer_size must be a positive integer")
        self._defaults = dict(defaults or {})
        self._event_buffer_size = event_buffer_size
        self._active_steps: set[asyncio.Task[Any]] = set()
        self._accepting = False
        self._plans = tuple(self._resolve_plan(app_context, raw) for raw in steps)
        super().__init__(app_context=app_context, **kwargs)

    @classmethod
    def _resolve_plan(
        cls,
        app_context: ApplicationContext | None,
        raw: ComponentConfig | Mapping[str, Any],
    ) -> StepPlan:
        config = ComponentConfig.model_validate(raw)
        if app_context is None:
            raise RuntimeError(
                f"{cls.__name__} needs an application context to resolve Steps"
            )
        step_class = app_context.registry.require(
            ComponentEnum.STEP, config.backend, BaseStep
        )
        options = config.model_dump()
        # Step instances are fresh per invocation, but construction is also the
        # configuration validation boundary. Validate once while building the
        # Job so an irrelevant or misspelled option cannot survive until runtime.
        step_class(app_context=app_context, **deepcopy(options))
        return StepPlan(step_class, options)

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
            yield plan.step_class(
                app_context=self.app_context, **deepcopy(plan.options)
            )

    @staticmethod
    async def _drain(
        events: asyncio.Queue[JobEvent],
        step_task: asyncio.Task[Any],
    ) -> AsyncIterator[JobEvent]:
        """Yield queued events until the Step finishes, without completion races."""
        while True:
            if step_task.done() and events.empty():
                await step_task
                return

            next_event = asyncio.create_task(events.get())
            try:
                done, _ = await asyncio.wait(
                    (step_task, next_event),
                    return_when=asyncio.FIRST_COMPLETED,
                )
            except BaseException:
                next_event.cancel()
                await asyncio.gather(next_event, return_exceptions=True)
                raise
            if next_event in done:
                yield next_event.result()
                continue

            next_event.cancel()
            await asyncio.gather(next_event, return_exceptions=True)
            while not events.empty():
                yield events.get_nowait()
            await step_task
            return

    async def stream(
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
                    async for event in self._drain(events, step_task):
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
