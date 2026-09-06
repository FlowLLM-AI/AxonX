"""Lifecycle-managed job scheduling."""

import asyncio
import math
from abc import ABC, abstractmethod
from contextlib import suppress
from typing import Any

from .base_job import BaseJob


class BaseScheduledJob(BaseJob, ABC):
    """Base class that runs one ordinary job invocation after each delay."""

    runs_in_background = True

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._runner: asyncio.Task[None] | None = None

    async def _start(self) -> None:
        await super()._start()
        self._runner = asyncio.create_task(
            self._run_forever(),
            name=f"axonx-job:{self.name}",
        )

    async def _run_forever(self) -> None:
        first_run = True
        while True:
            delay = self._next_delay(first_run)
            first_run = False
            if not math.isfinite(delay) or delay < 0:
                raise ValueError("Scheduled job delay must be finite and non-negative")
            if delay:
                await asyncio.sleep(delay)
            await super().__call__()

    @abstractmethod
    def _next_delay(self, first_run: bool) -> float:
        """Return the delay before the next invocation."""

    async def _close(self) -> None:
        runner, self._runner = self._runner, None
        try:
            if runner is not None:
                runner.cancel()
                with suppress(asyncio.CancelledError):
                    await runner
        finally:
            await super()._close()
