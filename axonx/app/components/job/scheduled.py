"""A pipeline Job that invokes itself at configured calendar times."""

import asyncio
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from croniter import croniter

from ...config.models import CronConfig
from ..registry import provider
from .pipeline import PipelineJob


@provider("scheduled")
class ScheduledJob(PipelineJob):
    """Run one scheduled invocation at a time, coalescing missed occurrences."""

    def __init__(self, expression: str, arguments: Mapping[str, Any] | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.expression = CronConfig.validate_expression(expression)
        self.arguments = deepcopy(dict(arguments or {}))
        self.validate_arguments(self.arguments)
        self.validate_system({})
        self.timezone = ZoneInfo(self.app_config.timezone)
        self._runner: asyncio.Task[None] | None = None

    async def _start(self) -> None:
        due = self._next_run()
        await super()._start()
        self._runner = asyncio.create_task(self._schedule(due), name=f"axonx-scheduled-job:{self.name}")

    async def _close(self) -> None:
        runner, self._runner = self._runner, None
        try:
            if runner is not None:
                await self._cancel_runs(runner)
                if not runner.cancelled():
                    runner.result()
        finally:
            await super()._close()

    def _next_run(self) -> datetime:
        return croniter(self.expression, datetime.now(self.timezone)).get_next(datetime)

    async def _schedule(self, due: datetime) -> None:
        while True:
            now = datetime.now(self.timezone)
            await asyncio.sleep(max(0, due.timestamp() - now.timestamp()))
            state = self.app_context.metadata
            if state.get("started") and not state.get("stopping") and not state.get("maintenance"):
                try:
                    response = await self.app_context.dispatcher.run(self.name, self.arguments)
                    if not response.success:
                        self.logger.warning(f"Scheduled Job failed: {response.answer}")
                except Exception:
                    self.logger.exception("Scheduled Job failed; retrying at the next scheduled time")
            due = self._next_run()
