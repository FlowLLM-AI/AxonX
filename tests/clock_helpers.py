"""Controllable wall and elapsed time for window and deadline tests."""

from datetime import UTC, timedelta

from axonx.task.core.clock import WindowClock


class FakeClock(WindowClock):
    def __init__(self, start):
        self.value = start.astimezone(UTC)
        self.elapsed = 0.0

    def now(self):
        return self.value

    def monotonic(self):
        return self.elapsed

    def sleep(self, seconds):
        self.value += timedelta(seconds=seconds)
        self.elapsed += seconds
