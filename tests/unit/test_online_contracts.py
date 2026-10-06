"""Deterministic window deadlines, audit persistence and comparison isolation."""

# Fake plugins acquire resources in initialize_run, matching the public lifecycle.
# pylint: disable=attribute-defined-outside-init

import json
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from axonx.task.contracts import (
    BaseInferenceTask,
    BasePredictionCompareTask,
    BaseRealtimeApiInputParams,
    BaseRealtimeApiTask,
    ExecutionWindow,
    PredictionComparison,
    WindowClock,
    WindowResult,
)
from axonx.task.runtime.runner import TaskRunner


class FakeClock(WindowClock):
    def __init__(self):
        self.seconds = 0
        self.origin = datetime(2026, 10, 5, tzinfo=UTC)

    def now(self):
        return self.origin + timedelta(seconds=self.seconds)

    def monotonic(self):
        return self.seconds

    def sleep(self, seconds):
        self.seconds += seconds


def window(clock, key="1445", start=0, end=5):
    return ExecutionWindow(
        key=key, start_at=clock.origin + timedelta(seconds=start), end_at=clock.origin + timedelta(seconds=end)
    )


class Collector(BaseRealtimeApiTask):
    def initialize_run(self):
        self.calls = 0
        self.closed = False

    def collect(self, item, budget):
        self.calls += 1
        if self.calls == 2:
            return WindowResult(key=item.key, status="done", rows=10, coverage=1)
        return None

    def close_run(self):
        self.closed = True


def run_task(cls, tmp_path, **params):
    clock = FakeClock()
    task = cls(
        {"task_name": "test", "windows": [window(clock)], **params}, workspace_path=tmp_path, reg_name="test_online"
    )
    task.clock = clock
    TaskRunner().run(task)
    return task


def test_wait_poll_skip_and_manifest(tmp_path):
    clock = FakeClock()
    task = run_task(Collector, tmp_path, windows=[window(clock, "past", -3, -1), window(clock, start=2)])
    assert task.calls == 2
    assert task.closed
    assert [item.status for item in task.output_params.windows] == ["skipped", "done"]
    assert task.clock.seconds == 3
    assert json.loads((task.task_dir / "manifest.json").read_text())["windows"][1]["coverage"] == 1
    assert task.output_params.artifacts["manifest"]["sha256"]


def test_poll_timeout_is_bounded(tmp_path):
    class Pending(Collector):
        def collect(self, item, budget):
            return None

    task = run_task(Pending, tmp_path, poll_interval_seconds=3)
    assert task.clock.seconds == 5
    assert task.output_params.windows[0].status == "incomplete"
    assert task.closed


def test_failed_window_audited_and_cleanup_preserves_error(tmp_path):
    class Broken(Collector):
        def collect(self, item, budget):
            raise ValueError("bad data")

        def close_run(self):
            self.closed = True
            raise RuntimeError("cleanup")

    clock = FakeClock()
    task = Broken({"task_name": "test", "windows": [window(clock)]}, workspace_path=tmp_path, reg_name="test_online")
    task.clock = clock
    with pytest.raises(ValueError, match="bad data"):
        TaskRunner().run(task)
    assert task.closed
    report = json.loads((task.task_dir / "manifest.json").read_text())
    assert report["windows"][0]["status"] == "failed"
    assert not task.metadata_path.exists()


def test_inference_resolves_once_and_never_predicts_missing_inputs(tmp_path):
    class Inference(BaseInferenceTask):
        def initialize_run(self):
            self.model_identity = {"fingerprint": "fixed"}
            self.predicted = []

        def inputs_ready(self, item):
            return item.key == "ready"

        def infer(self, item, budget):
            self.predicted.append(item.key)
            return WindowResult(key=item.key, status="done", rows=2)

    clock = FakeClock()
    task = run_task(Inference, tmp_path, windows=[window(clock, "ready"), window(clock, "missing", end=8)])
    assert task.predicted == ["ready"]
    assert task.output_params.windows[1].reason == "inputs_timeout"
    assert task.output_params.model_identity == {"fingerprint": "fixed"}


def test_late_completion_cannot_claim_done(tmp_path):
    class Late(Collector):
        def collect(self, item, budget):
            self.clock.sleep(10)
            return WindowResult(key=item.key, status="done")

    task = run_task(Late, tmp_path)
    assert task.output_params.windows[0].status == "incomplete"


def test_comparison_isolates_errors_and_protocol_mismatch(tmp_path):
    class Compare(BasePredictionCompareTask):
        def compare(self, key):
            if key == "broken":
                raise FileNotFoundError("missing source")
            return PredictionComparison(key=key, status="protocol_mismatch" if key == "model" else "consistent")

    task = Compare(
        {"task_name": "test", "comparison_keys": ["broken", "model", "ok"]},
        workspace_path=tmp_path,
        reg_name="test_compare",
    )
    TaskRunner().run(task)
    assert [item.status for item in task.output_params.comparisons] == ["error", "protocol_mismatch", "consistent"]
    assert task.output_params.artifacts["comparison"]["path"] == "comparison.json"


def test_window_validation():
    clock = FakeClock()
    with pytest.raises(ValidationError):
        ExecutionWindow(key="x", start_at=datetime(2026, 1, 1), end_at=datetime(2026, 1, 2))
    with pytest.raises(ValidationError, match="unique"):
        BaseRealtimeApiInputParams(windows=[window(clock), window(clock)])
    with pytest.raises(ValidationError):
        BaseRealtimeApiInputParams(windows=[window(clock)], poll_interval_seconds=float("inf"))


def test_initialization_failure_still_closes_resources(tmp_path):
    class InitFailure(Collector):
        def initialize_run(self):
            raise ValueError("cannot initialize")

    clock = FakeClock()
    task = InitFailure(
        {"task_name": "test", "windows": [window(clock)]}, workspace_path=tmp_path, reg_name="test_online"
    )
    task.clock = clock
    with pytest.raises(ValueError, match="cannot initialize"):
        TaskRunner().run(task)
    assert task.closed


def test_cancellation_is_not_swallowed(tmp_path):
    class Interrupted(Collector):
        def collect(self, item, budget):
            raise KeyboardInterrupt()

    clock = FakeClock()
    task = Interrupted(
        {"task_name": "test", "windows": [window(clock)]}, workspace_path=tmp_path, reg_name="test_online"
    )
    task.clock = clock
    with pytest.raises(KeyboardInterrupt):
        TaskRunner().run(task)
    assert task.closed


@pytest.mark.parametrize("skip_seconds", [0, 2])
def test_business_skip_happens_before_future_window_wait(tmp_path, skip_seconds):
    class Closed(Collector):
        def window_skip_reason(self, item):
            self.clock.sleep(skip_seconds)
            return "market_closed"

    clock = FakeClock()
    task = run_task(Closed, tmp_path, windows=[window(clock, start=3600, end=3605)])
    assert task.clock.seconds == skip_seconds
    assert task.calls == 0
    assert task.closed
    assert task.output_params.windows[0].reason == "market_closed"
    assert task.output_params.windows[0].elapsed_seconds == skip_seconds
    report = json.loads((task.task_dir / "manifest.json").read_text())
    assert report["windows"][0]["status"] == "skipped"
    assert report["windows"][0]["elapsed_seconds"] == skip_seconds
