"""Trigger daemon-owned commands while the application is running."""

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import datetime
from zoneinfo import ZoneInfo

from croniter import croniter

from ...config.models import CronConfig
from ..base import BaseComponent
from ..models import ComponentType

ScheduledLaunch = Callable[[int, CronConfig], Awaitable[None]]


class CronComponent(BaseComponent):
    """Own future triggers; launched processes belong to the daemon."""

    component_type = ComponentType.CRON

    def __init__(
        self,
        launch: ScheduledLaunch,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.entries = self.app_config.cron
        self.timezone = ZoneInfo(self.app_config.timezone)
        self._launch = launch
        self._next: list[datetime] = []
        self._runner: asyncio.Task | None = None

    async def _start(self) -> None:
        now = datetime.now(self.timezone)
        self._next = [croniter(entry.expression, now).get_next(datetime) for entry in self.entries]
        self._runner = asyncio.create_task(self._run(), name="axonx-cron")

    async def _close(self) -> None:
        if self._runner is not None:
            self._runner.cancel()
            with suppress(asyncio.CancelledError):
                await self._runner
            self._runner = None
        self._next.clear()

    async def _run(self) -> None:
        while True:
            await self._tick(datetime.now(self.timezone))
            await asyncio.sleep(0.5)

    async def _tick(self, now: datetime) -> None:
        for index, entry in enumerate(self.entries):
            if self.app_context.metadata.get("stopping") or self.app_context.metadata.get("maintenance"):
                return
            if self._next[index].timestamp() > now.timestamp():
                continue
            # Advance before requesting a launch: failed or ambiguous requests are not replayed.
            self._next[index] = croniter(entry.expression, now).get_next(datetime)
            try:
                await self._launch(index, entry)
            except (OSError, RuntimeError):
                self.logger.exception(f"Cron launch failed: cron[{index}]")
