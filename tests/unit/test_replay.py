"""Replay protects causal visibility, file identity and child clock ownership."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import json
from time import sleep

import pytest

from axonx.enums import TaskState
from axonx.task import BaseCompositeTask
from axonx.task.builtins.demo import DemoTask
from axonx.task.clock import ReplayClock
from axonx.task.contracts import DeadlineBudget
from axonx.task.replay import ReplayCursor, ReplaySource, ReplayStream
from axonx.task.runtime.runner import TaskRunner


@pytest.fixture
def stream(tmp_path):
    payload = tmp_path / "data.csv"
    payload.write_text("code,price\nA,10\n")
    start = datetime(2024, 1, 2, 1, 30, tzinfo=UTC)
    result = ReplayStream.create(
        tmp_path / "stream",
        [ReplaySource(key, start + timedelta(hours=i), {"data": payload}) for i, key in enumerate(["open", "bar"])],
    )
    return result


def test_cursor_releases_only_available_events_and_keeps_deadline_exclusive(stream):
    start = stream.manifest.events[0].available_at
    clock = ReplayClock(start)
    cursor = ReplayCursor(stream, clock)
    delivered = []

    def consume(event):
        assert event.available_at <= clock.now()
        delivered.append(event.key)

    assert cursor.wait(start + timedelta(minutes=1), consume, lambda: len(delivered) == 1)
    assert delivered == ["open"]
    assert clock.now() == start
    assert not cursor.wait(start + timedelta(hours=1), consume, lambda: len(delivered) == 2)
    assert delivered == ["open"]
    assert cursor.wait(start + timedelta(hours=2), consume, lambda: len(delivered) == 2)
    assert delivered == ["open", "bar"]
    assert clock.monotonic() == 3600


def test_computation_pauses_simulated_time_but_waits_consume_budget():
    clock = ReplayClock(datetime(2024, 1, 2, tzinfo=UTC))
    budget = DeadlineBudget(clock, clock.now() + timedelta(seconds=2))
    sleep(0.02)
    assert budget.remaining_seconds == 2
    budget.sleep(3)
    assert budget.remaining_seconds == 0
    with pytest.raises(TimeoutError):
        budget.check()
    with pytest.raises(ValueError):
        clock.advance_to(clock.now() - timedelta(seconds=1))
    with pytest.raises(ValueError):
        clock.sleep(float("inf"))


def test_worker_cannot_advance_driver_clock():
    clock = ReplayClock(datetime(2024, 1, 2, tzinfo=UTC))
    with ThreadPoolExecutor(1) as pool:
        with pytest.raises(RuntimeError, match="replay driver"):
            pool.submit(clock.sleep, 1).result()
    assert clock.monotonic() == 0


def test_task_preserves_existing_class_clock_override(tmp_path):
    clock = ReplayClock(datetime(2024, 1, 2, tzinfo=UTC))

    class Custom(DemoTask):
        pass

    Custom.clock = clock
    task = Custom({"x": 1, "y": 2}, workspace_path=tmp_path, reg_name="custom")
    assert task.clock is clock


def test_stream_copies_inputs_and_rejects_mutated_payload(stream, tmp_path):
    original = tmp_path / "data.csv"
    original.write_text("changed")
    record = stream.manifest.events[0].files["data"]
    assert stream.file(record).read_text() == "code,price\nA,10\n"
    stream.file(record).write_text("corrupted")
    with pytest.raises(ValueError, match="changed"):
        ReplayStream(stream.root)


def test_stream_rejects_path_escape_and_unordered_events(stream, tmp_path):
    manifest = stream.root / "stream.json"
    data = json.loads(manifest.read_text())
    data["events"].reverse()
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="ordered"):
        ReplayStream(stream.root)
    data["events"].reverse()
    data["events"][0]["files"]["data"]["path"] = str(tmp_path / "data.csv")
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="relative.*path|escapes"):
        ReplayStream(stream.root)


def test_child_and_nested_child_inherit_business_clock_but_lifecycle_is_real(tmp_path, monkeypatch):
    clock = ReplayClock(datetime(2024, 1, 2, tzinfo=UTC))
    observed = []

    class Child(DemoTask):
        def finish(self):
            observed.append(self.clock)
            self.clock.sleep(60)
            super().finish()

    class Nested(BaseCompositeTask):
        def build_task_steps(self):
            yield self.children_step

        def children_step(self):
            self.run_task("child", x=1, y=2)

    class Parent(Nested):
        def children_step(self):
            self.run_task("nested")

    monkeypatch.setattr(
        "axonx.task.catalog.resolver.resolve_task",
        lambda name: Child if name == "child" else Nested,
    )
    task = Parent({}, workspace_path=tmp_path, reg_name="parent", clock=clock)
    wall_started = datetime.now(UTC)
    status = TaskRunner().run(task)
    assert status.state == TaskState.SUCCEEDED
    assert observed == [clock]
    assert clock.monotonic() == 60
    assert status.started_at >= wall_started
