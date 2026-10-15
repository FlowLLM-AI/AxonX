"""Business clocks; lifecycle timestamps and performance measurements stay real."""

from datetime import UTC, datetime, timedelta
from math import isfinite
from threading import get_ident
import time


class WindowClock:
    """Wall time and monotonic time used by business windows and budgets."""

    def now(self) -> datetime:
        return datetime.now(UTC)

    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


class ReplayClock(WindowClock):
    """Single-driver clock: only explicit waits advance time; computation is free.

    Read access is allowed from workers, but only the creating thread may advance
    time. This prevents independent background waits from racing the event driver.
    """

    def __init__(self, start_at: datetime):
        if start_at.tzinfo is None or start_at.utcoffset() is None:
            raise ValueError("Replay clock requires an aware start time")
        self._start = self._now = start_at.astimezone(UTC)
        self._owner = get_ident()

    def now(self) -> datetime:
        return self._now

    def monotonic(self) -> float:
        return (self._now - self._start).total_seconds()

    def advance_to(self, target: datetime) -> None:
        if get_ident() != self._owner:
            raise RuntimeError("Only the replay driver may advance time")
        if target.tzinfo is None or target.utcoffset() is None or target < self._now:
            raise ValueError("Replay time must be aware and cannot move backwards")
        self._now = target.astimezone(UTC)

    def sleep(self, seconds: float) -> None:
        if not isfinite(seconds) or seconds < 0:
            raise ValueError("Replay sleep must be finite and nonnegative")
        self.advance_to(self._now + timedelta(seconds=seconds))
