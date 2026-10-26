"""Business clocks; lifecycle timestamps and performance measurements stay real."""

import time
from datetime import UTC, datetime


class WindowClock:
    """Wall time and monotonic time used by business windows and budgets."""

    def now(self) -> datetime:
        return datetime.now(UTC)

    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


class DeadlineBudget:
    """Plugins must bound request timeouts, retries and backoff by remaining seconds."""

    def __init__(self, clock: WindowClock, end_at: datetime):
        if end_at.tzinfo is None or end_at.utcoffset() is None:
            raise ValueError("Window deadline requires an aware time")
        self.clock = clock
        started = clock.monotonic()
        seconds = (end_at.astimezone(UTC) - clock.now().astimezone(UTC)).total_seconds()
        self.deadline = started + max(0, seconds)

    @property
    def remaining_seconds(self) -> float:
        return max(0, self.deadline - self.clock.monotonic())

    def sleep(self, seconds: float) -> None:
        self.clock.sleep(max(0, min(seconds, self.remaining_seconds)))

    def check(self) -> None:
        """Fail before beginning or publishing work after the deadline."""
        if self.remaining_seconds <= 0:
            raise TimeoutError("Window deadline exceeded")
