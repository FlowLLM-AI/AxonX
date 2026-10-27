"""Trigger daemon-owned commands while the application is running."""

import asyncio
from contextlib import suppress
from datetime import datetime
from zoneinfo import ZoneInfo

from croniter import croniter

from .base import BaseCronComponent, ScheduledLaunch


class CronComponent(BaseCronComponent):
    """Own future triggers; launched processes belong to the daemon."""

    def __init__(
        self,
        launch: ScheduledLaunch,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.entries = tuple(self.app_config.cron)
        self.timezone = ZoneInfo(self.app_config.timezone)
        self._launch = launch
        self._next: list[datetime] = []
        self._runner: asyncio.Task[None] | None = None

    async def _start(self) -> None:
        now = datetime.now(self.timezone)
        self._next = [croniter(entry.expression, now).get_next(datetime) for entry in self.entries]
        if self.entries:
            self._runner = asyncio.create_task(self._run(), name="axonx-cron")

    async def _close(self) -> None:
        runner, self._runner = self._runner, None
        try:
            if runner is not None:
                runner.cancel()
                with suppress(asyncio.CancelledError):
                    await runner
        finally:
            self._next.clear()

    async def _run(self) -> None:
        while True:
            await self.tick(datetime.now(self.timezone))
            await asyncio.sleep(0.5)

    async def tick(self, now: datetime) -> None:
        """Trigger each due entry once, without replaying missed occurrences."""
        if now.utcoffset() is None:
            raise ValueError("Cron tick requires a timezone-aware datetime")
        now = now.astimezone(self.timezone)
        timestamp = now.timestamp()
        for index, entry in enumerate(self.entries):
            if self.app_context.metadata.get("stopping") or self.app_context.metadata.get("maintenance"):
                return
            if self._next[index].timestamp() > timestamp:
                continue
            # Advance before requesting a launch: failed or ambiguous requests are not replayed.
            self._next[index] = croniter(entry.expression, now).get_next(datetime)
            try:
                await self._launch(index, entry)
            except Exception:  # A host callback failure must not stop other schedules.
                self.logger.exception(f"Cron launch failed: cron[{index}]")
