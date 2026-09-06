"""Cron-scheduled background jobs."""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .base_scheduled_job import BaseScheduledJob
from ..component_registry import R


@R.register("cron")
class CronJob(BaseScheduledJob):
    """Run at times selected by a cron expression in the application timezone."""

    def __init__(self, cron: str, **kwargs: Any) -> None:
        from croniter import croniter

        if not isinstance(cron, str) or not croniter.is_valid(cron):
            raise ValueError(f"Invalid cron expression: {cron!r}")
        super().__init__(**kwargs)
        timezone = self.app_context.app_config.timezone
        try:
            self.timezone = ZoneInfo(timezone)
        except ZoneInfoNotFoundError:
            raise ValueError(f"Unknown timezone: {timezone!r}") from None
        self.cron = cron

    def _next_delay(self, _first_run: bool) -> float:
        from croniter import croniter

        now = datetime.now(self.timezone)
        next_run = croniter(self.cron, now).get_next(datetime)
        return max(0.0, (next_run - now).total_seconds())
