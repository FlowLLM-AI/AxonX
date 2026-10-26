"""Trigger daemon-owned commands while the application is running."""

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from contextlib import suppress
from datetime import datetime
from zoneinfo import ZoneInfo

from ..base import BaseComponent
from ..component_type import ComponentType
from ...registry import provider
from .parser import CronEntry, load_crontab


@provider("cron")
class CronComponent(BaseComponent):
    """Own future triggers; launched processes belong to the daemon."""

    component_type = ComponentType.CRON

    def __init__(
        self,
        source: str,
        launch: Callable[[CronEntry], Awaitable[None]],
        validate_command: Callable[[Sequence[str]], None],
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.path, self.entries = load_crontab(source, validate_command)
        self.timezone = ZoneInfo(self.app_config.timezone)
        self._launch = launch
        self._next: dict[int, datetime] = {}
        self._runner: asyncio.Task | None = None

    async def _start(self) -> None:
        now = datetime.now(self.timezone)
        self._next = {entry.line: entry.next_after(now) for entry in self.entries}
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
        for entry in self.entries:
            if self.app_context.metadata.get("stopping") or self.app_context.metadata.get("maintenance"):
                return
            if self._next[entry.line].timestamp() > now.timestamp():
                continue
            # Advance before requesting a launch: failed or ambiguous requests are not replayed.
            self._next[entry.line] = entry.next_after(now)
            try:
                await self._launch(entry)
            except (OSError, RuntimeError):
                self.logger.exception(f"Cron launch failed: {self.path}:{entry.line}")
