"""Cron-scheduled background jobs."""

import asyncio
from contextlib import suppress
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .base_job import BaseJob
from ..component_registry import R


@R.register("cron")
class CronJob(BaseJob):
    """Run at times selected by a cron expression in the application timezone."""

    runs_in_background = True

    def __init__(self, cron: str, **kwargs: Any) -> None:
        from croniter import croniter

        if not isinstance(cron, str) or not croniter.is_valid(cron):
            raise ValueError(f"Invalid cron expression: {cron!r}")
        super().__init__(**kwargs)
        timezone = self.app_config.timezone
        try:
            self.timezone = ZoneInfo(timezone)
        except ZoneInfoNotFoundError:
            raise ValueError(f"Unknown timezone: {timezone!r}") from None
        self.cron = cron
        self._runner: asyncio.Task[None] | None = None

    async def _start(self) -> None:
        await super()._start()
        self._runner = asyncio.create_task(
            self._run_forever(),
            name=f"axonx-job:{self.name}",
        )

    async def _run_forever(self) -> None:
        while True:
            await asyncio.sleep(self._next_delay())
            await super().__call__()

    def _next_delay(self) -> float:
        from croniter import croniter

        now = datetime.now(self.timezone)
        next_run = croniter(self.cron, now).get_next(datetime)
        return max(0.0, (next_run - now).total_seconds())

    async def _close(self) -> None:
        runner, self._runner = self._runner, None
        try:
            if runner is not None:
                runner.cancel()
                with suppress(asyncio.CancelledError):
                    await runner
        finally:
            await super()._close()
