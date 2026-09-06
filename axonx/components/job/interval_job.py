"""Fixed-delay background jobs."""

import math
from typing import Any

from .base_scheduled_job import BaseScheduledJob
from ..component_registry import R


@R.register("interval")
class IntervalJob(BaseScheduledJob):
    """Run immediately and then wait a fixed delay between invocations."""

    def __init__(self, interval: float = 1.0, **kwargs: Any) -> None:
        if (
            isinstance(interval, bool)
            or not isinstance(interval, (int, float))
            or not math.isfinite(interval)
            or interval <= 0
        ):
            raise ValueError("interval must be a positive finite number")
        super().__init__(**kwargs)
        self.interval = float(interval)

    def _next_delay(self, first_run: bool) -> float:
        return 0.0 if first_run else self.interval
