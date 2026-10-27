"""Backend-neutral scheduling contract and injected command launcher."""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from datetime import datetime

from ...config.models import CronConfig
from ..base import BaseComponent

ScheduledLaunch = Callable[[int, CronConfig], Awaitable[None]]


class BaseCronComponent(BaseComponent, ABC):
    """Own application schedules while the host owns launched processes."""

    component_type = "cron"

    @abstractmethod
    async def tick(self, now: datetime) -> None:
        """Launch due entries at an aware instant, coalescing missed occurrences.

        Advance each entry before launching it, isolate launch failures, and
        stop admitting launches while the application is stopping or updating.
        """
