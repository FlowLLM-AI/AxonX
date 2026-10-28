"""Drive deterministic business time and deliver recorded replay events."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from math import isfinite
from threading import get_ident
from typing import TYPE_CHECKING

from ..core.clock import WindowClock
from ..models.artifacts import ReplayEvent

if TYPE_CHECKING:
    from ..storage.replay import ReplayStream


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


class ReplayCursor:
    """Deliver events only when available and strictly before the caller's deadline."""

    def __init__(self, stream: ReplayStream, clock: ReplayClock):
        self.stream, self.clock, self.position = stream, clock, 0

    def wait(
        self,
        deadline: datetime,
        consume: Callable[[ReplayEvent], None],
        ready: Callable[[], bool],
    ) -> bool:
        while self.clock.now() < deadline:
            if ready():
                return True
            if self.position == len(self.stream.manifest.events):
                break
            event = self.stream.manifest.events[self.position]
            if event.available_at >= deadline:
                break
            self.clock.advance_to(max(self.clock.now(), event.available_at))
            consume(event)
            self.position += 1
        if self.clock.now() < deadline:
            self.clock.advance_to(deadline)
        return False
