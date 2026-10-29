"""Ordered, streaming Step pipeline Job."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from contextlib import aclosing
from copy import deepcopy
from typing import TYPE_CHECKING, Any

from ....client.events import JobEvent, ResultEvent
from ....client.models import JobResponse
from ....utils.async_work import complete_on_cancel
from ...config.loader import deep_merge_config
from ...config.models import ComponentConfig
from ..registry import provider
from .base import BaseJob

if TYPE_CHECKING:
    from ...core.context import ApplicationContext
    from ...steps.base import BaseStep


class _RuntimeContext(dict[str, Any]):
    """Combine defaults, caller arguments, and system data for Job Steps."""

    def __init__(
        self,
        defaults: Mapping[str, Any],
        arguments: Mapping[str, Any],
        system: Mapping[str, Any],
    ) -> None:
        values = deep_merge_config(defaults, arguments)
        super().__init__(deepcopy(deep_merge_config(values, system)))
        self.response = JobResponse()


@provider("pipeline")
class PipelineJob(BaseJob):
    """Run fresh Steps in one invocation task feeding a bounded event stream."""

    def __init__(
        self,
        *,
        app_context: ApplicationContext,
        steps: Sequence[ComponentConfig | Mapping[str, Any]] = (),
        defaults: Mapping[str, Any] | None = None,
        event_buffer_size: int = 64,
        cancel_on_disconnect: bool = True,
        **kwargs,
    ) -> None:
        if isinstance(event_buffer_size, bool) or not isinstance(event_buffer_size, int) or event_buffer_size < 1:
            raise ValueError("event_buffer_size must be a positive integer")
        if not isinstance(cancel_on_disconnect, bool):
            raise ValueError("cancel_on_disconnect must be a boolean")
        self._defaults = deepcopy(dict(defaults or {}))
        self._event_buffer_size = event_buffer_size
        self._cancel_on_disconnect = cancel_on_disconnect
        self._active_runs: set[asyncio.Task[None]] = set()
        self._accepting = False
        self._steps = tuple(self._resolve_step(app_context, raw) for raw in steps)
        super().__init__(app_context=app_context, **kwargs)

    @staticmethod
    def _resolve_step(
        app_context: ApplicationContext,
        raw: ComponentConfig | Mapping[str, Any],
    ) -> tuple[type[BaseStep], dict[str, Any]]:
        from ...steps.base import BaseStep

        config = ComponentConfig.model_validate(raw)
        step_class = app_context.registry.require(BaseStep.component_type, config.backend, BaseStep)
        return step_class, config.model_dump()

    def _injected_parameters(self) -> Mapping[str, Any]:
        merged: dict[str, Any] = {}
        for step_class, _ in self._steps:
            for name, schema in step_class.injected_parameters.items():
                if name in merged and merged[name] != schema:
                    raise ValueError(f"Conflicting injected Job parameter: {name!r}")
                merged[name] = schema
        return merged

    async def _start(self) -> None:
        self._accepting = True

    async def _close(self) -> None:
        self._accepting = False
        await self._cancel_runs(*self._active_runs)

    @staticmethod
    async def _cancel_runs(*tasks: asyncio.Task[None]) -> None:
        """Share cancellation and wait for cleanup without interrupting it a second time."""
        for task in tasks:
            if not task.cancelling():
                task.cancel()
        await complete_on_cancel(asyncio.gather(*tasks, return_exceptions=True))

    @staticmethod
    async def _drain(
        events: asyncio.Queue[JobEvent],
        task: asyncio.Task[None],
    ) -> AsyncIterator[JobEvent]:
        """Drain the bounded queue, then propagate execution failures or cancellation."""
        while not task.done() or not events.empty():
            if not events.empty():
                yield events.get_nowait()
                continue
            next_event = asyncio.create_task(events.get())
            try:
                done, _ = await asyncio.wait(
                    (task, next_event),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if next_event in done:
                    yield next_event.result()
            finally:
                next_event.cancel()
                await asyncio.gather(next_event, return_exceptions=True)
        await task

    async def _execute(
        self,
        context: _RuntimeContext,
        emit: Callable[[JobEvent], Awaitable[None]],
    ) -> None:
        """Run the whole invocation in one owned task, with fresh Step instances."""
        try:
            for step_class, options in self._steps:
                step = step_class(app_context=self.app_context, **deepcopy(options))
                await step(context, emit)
                if not context.response.success:
                    break
        except Exception as exc:
            if isinstance(exc, ValueError):
                self.logger.warning(f"Job failed: {type(exc).__name__}: {exc}")
            else:
                self.logger.exception("Job failed")
            context.response.fail(exc)
        await emit(ResultEvent.from_response(context.response))

    # Async generators satisfy the base contract returning an AsyncIterator.
    async def stream(  # pylint: disable=invalid-overridden-method
        self,
        arguments: Mapping[str, Any],
        system: Mapping[str, Any],
    ) -> AsyncIterator[JobEvent]:
        if not self._accepting:
            raise RuntimeError(f"Job {self.name!r} is not running")

        context = _RuntimeContext(self._defaults, arguments, system)
        events: asyncio.Queue[JobEvent] = asyncio.Queue(self._event_buffer_size)
        observing = True

        async def emit(event: JobEvent) -> None:
            if observing:
                await events.put(event)
            if not observing:
                # Release writers already blocked on a full queue at disconnect.
                while not events.empty():
                    events.get_nowait()
                # Keep a busy producer interruptible by Job/application shutdown.
                await asyncio.sleep(0)

        task = asyncio.create_task(self._execute(context, emit), name=f"axonx-job:{self.name}")
        self._active_runs.add(task)
        task.add_done_callback(self._active_runs.discard)
        try:
            async with aclosing(self._drain(events, task)) as stream:
                async for event in stream:
                    yield event
        finally:
            observing = False
            while not events.empty():
                events.get_nowait()
            if self._cancel_on_disconnect:
                await self._cancel_runs(task)
