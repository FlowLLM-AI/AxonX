"""Verify authoring extensions through the real Runner and deterministic business time."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from axonx.task.core.clock import DeadlineBudget, WindowClock
from axonx.task.core.standard import BasePredictionCompareTask
from axonx.task.core.windows import BaseInferenceTask, BaseRealtimeApiTask
from axonx.task.models.identity import TaskState
from axonx.task.models.params import ExecutionWindow, WindowInputParams
from axonx.task.models.reports import PredictionComparison, WindowResult
from axonx.task.runtime.replay import ReplayClock
from axonx.task.runtime.runner import TaskRunner
from axonx.task.storage.workspace import read_entry
from axonx.utils.logging import LoggingConfig, configure_logging

START = datetime(2001, 1, 1, tzinfo=UTC)


def window(key="first", start=0, end=5):
    return ExecutionWindow(key=key, start_at=START + timedelta(seconds=start), end_at=START + timedelta(seconds=end))


class CollectorTask(BaseRealtimeApiTask):
    def initialize_run(self):
        self.state["calls"] = []

    def collect(self, window, budget):
        self.state["calls"].append((window.key, self.clock.now()))
        return WindowResult(key=window.key, status="done")

    def close(self):
        self.state["closed"] = self.state.get("closed", 0) + 1


class InferenceTask(BaseInferenceTask):
    model_identity: dict[str, str]

    def initialize_run(self):
        self.model_identity = {"fingerprint": "fixed"}

    def inputs_ready(self, window):
        return True

    def infer(self, window, budget):
        return WindowResult(key=window.key, status="done")


@pytest.fixture
def make_task(tmp_path):
    configure_logging(LoggingConfig(log_to_console=False, log_to_file=False))

    def create(cls=CollectorTask, windows=None, **inputs):
        return cls(
            {"windows": windows or [window()], **inputs},
            workspace_path=tmp_path,
            reg_name="test",
            clock=ReplayClock(START),
        )

    return create


def test_windows_skip_missed_and_business_exclusions_then_wait_for_start(make_task):
    class Collector(CollectorTask):
        def window_skip_reason(self, window):
            return "market_closed" if window.key == "closed" else None

    task = make_task(Collector, [window("missed", -3, -2), window("closed", -1, 0), window("ready", 2, 5)])
    status = TaskRunner().run(task)
    results = task.output_params.windows
    assert [result.status for result in results] == ["skipped", "skipped", "done"]
    assert [result.reason for result in results[:2]] == ["window_missed", "market_closed"]
    assert task.state["calls"] == [("ready", START + timedelta(seconds=2))]
    assert results[-1].elapsed_seconds == 2
    assert task.state["closed"] == 1
    assert status.state == TaskState.SUCCEEDED
    assert status.started_at > START + timedelta(days=1)
    assert status.output_params == read_entry(task.workspace_path, task.task_id).output_params


def test_window_failure_retains_completed_and_failed_results_and_stops(make_task):
    class Collector(CollectorTask):
        def collect(self, window, budget):
            if window.key == "second":
                raise RuntimeError("collection failed")
            return super().collect(window, budget)

    task = make_task(Collector, [window(), window("second", 5, 10), window("third", 10, 15)])
    with pytest.raises(RuntimeError, match="collection failed"):
        TaskRunner().run(task)
    status = read_entry(task.workspace_path, task.task_id)
    assert status.state == TaskState.FAILED
    assert [(result["key"], result["status"]) for result in status.output_params["windows"]] == [
        ("first", "done"),
        ("second", "failed"),
    ]
    assert task.state["closed"] == 1
    assert task.clock.now() == START + timedelta(seconds=5)


@pytest.mark.parametrize("stage", ["initialize_run", "validate_run"])
@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_window_setup_failure_always_cleans_once_and_preserves_primary_error(make_task, stage, cleanup_fails):
    class Collector(CollectorTask):
        def close(self):
            super().close()
            if cleanup_fails:
                raise OSError("cleanup failed")

    def fail(self):
        raise ValueError("setup failed")

    setattr(Collector, stage, fail)
    task = make_task(Collector)
    with pytest.raises(ValueError, match="setup failed"):
        TaskRunner().run(task)
    assert task.state["closed"] == 1
    assert "setup failed" in read_entry(task.workspace_path, task.task_id).error


def test_window_cleanup_failure_leaves_the_task_failed_with_its_business_output(make_task):
    class Collector(CollectorTask):
        def close(self):
            super().close()
            raise OSError("cleanup failed")

    task = make_task(Collector)
    with pytest.raises(OSError, match="cleanup failed"):
        TaskRunner().run(task)
    status = read_entry(task.workspace_path, task.task_id)
    assert status.state == TaskState.FAILED
    assert status.output_params["windows"][0]["status"] == "done"
    assert task.state["closed"] == 1


@pytest.mark.parametrize("case", ["wrong_key", "outside_commit", "late", "committed"])
def test_window_result_keys_commits_and_deadlines(make_task, case):
    class Collector(CollectorTask):
        def collect(self, window, budget):
            values = {"key": window.key, "status": "done"}
            if case == "wrong_key":
                values["key"] = "other"
            if case in {"outside_commit", "committed"}:
                values.update(
                    commit_id="a" * 32,
                    committed_at=window.end_at + timedelta(seconds=1 if case == "outside_commit" else -1),
                )
            if case in {"late", "committed"}:
                self.clock.sleep(6)
            return WindowResult(**values)

    task = make_task(Collector)
    if case in {"wrong_key", "outside_commit"}:
        with pytest.raises(ValueError):
            TaskRunner().run(task)
        assert read_entry(task.workspace_path, task.task_id).output_params["windows"][0]["status"] == "failed"
    else:
        TaskRunner().run(task)
        result = task.output_params.windows[0]
        assert result.status == ("incomplete" if case == "late" else "done")
        assert result.elapsed_seconds == 6
        if case == "late":
            assert result.reason == "deadline_exceeded"


def test_realtime_polling_stops_at_deadline_without_marking_the_task_failed(make_task):
    class Collector(CollectorTask):
        def collect(self, window, budget):
            self.state["calls"].append((window.key, self.clock.now()))

    task = make_task(Collector, poll_interval_seconds=2)
    assert TaskRunner().run(task).state == TaskState.SUCCEEDED
    assert [at for _, at in task.state["calls"]] == [START + timedelta(seconds=n) for n in (0, 2, 4)]
    assert task.clock.now() == window().end_at
    assert task.output_params.windows[0].status == "incomplete"


@pytest.mark.parametrize("ready_at", [2, 5, None])
def test_inference_waits_for_inputs_and_never_starts_inference_at_deadline(make_task, ready_at):
    class Inference(InferenceTask):
        def inputs_ready(self, window):
            if ready_at is None:
                return False
            self.clock.sleep(ready_at)
            return True

        def infer(self, window, budget):
            self.state["inferred"] = True
            return super().infer(window, budget)

    task = make_task(Inference)
    TaskRunner().run(task)
    assert task.output_params.model_identity == {"fingerprint": "fixed"}
    assert task.output_params.windows[0].status == ("done" if ready_at == 2 else "incomplete")
    assert task.state.get("inferred", False) == (ready_at == 2)
    if ready_at != 2:
        assert task.output_params.windows[0].reason == "inputs_timeout"


@pytest.mark.parametrize("stage", ["waiting", "ready", "infer"])
def test_inference_rejects_model_identity_mutation_in_every_extension(make_task, stage):
    class Inference(InferenceTask):
        def inputs_ready(self, window):
            if stage != "infer":
                self.model_identity["fingerprint"] = "changed"
            return stage != "waiting"

        def infer(self, window, budget):
            self.model_identity["fingerprint"] = "changed"
            return super().infer(window, budget)

    task = make_task(Inference)
    with pytest.raises(ValueError, match="Model identity changed"):
        TaskRunner().run(task)
    status = read_entry(task.workspace_path, task.task_id)
    assert status.output_params["model_identity"] == {"fingerprint": "fixed"}
    assert status.output_params["windows"][0]["status"] == "failed"


@pytest.mark.parametrize("identity", [None, {}, {"fingerprint": 42}])
def test_inference_requires_a_valid_model_identity(make_task, identity):
    class Inference(InferenceTask):
        model_identity: dict[str, str]

        def initialize_run(self):
            self.model_identity = identity

    with pytest.raises(ValueError):
        TaskRunner().run(make_task(Inference))


def test_comparison_errors_and_wrong_keys_are_reported_without_losing_other_results(tmp_path):
    class CompareTask(BasePredictionCompareTask):
        def compare(self, key):
            if key == "error":
                raise OSError("input unavailable")
            return PredictionComparison(key="other" if key == "wrong" else key, status="consistent")

    task = CompareTask({"comparison_keys": ["ok", "error", "wrong"]}, workspace_path=tmp_path, reg_name="compare")
    assert TaskRunner().run(task).state == TaskState.SUCCEEDED
    assert [result.status for result in task.output_params.comparisons] == ["consistent", "error", "error"]
    assert "input unavailable" in task.output_params.comparisons[1].reason
    assert task.output == read_entry(tmp_path, task.task_id).output_params


def test_deadline_budget_uses_elapsed_seconds_across_repeated_local_time():
    zone = ZoneInfo("America/New_York")
    start = datetime(2026, 11, 1, 1, 45, tzinfo=zone, fold=0)
    end = datetime(2026, 11, 1, 1, 15, tzinfo=zone, fold=1)

    class LocalClock(ReplayClock):
        def now(self):
            return super().now().astimezone(zone)

    clock = LocalClock(start)
    budget = DeadlineBudget(clock, end)
    assert budget.remaining_seconds == 1800
    budget.sleep(3600)
    assert budget.remaining_seconds == 0
    assert clock.now().astimezone(UTC) == end.astimezone(UTC)
    with pytest.raises(TimeoutError):
        budget.check()
    assert ExecutionWindow(key="fold", start_at=start, end_at=end)
    with pytest.raises(ValueError, match="after start_at"):
        ExecutionWindow(key="reversed", start_at=end, end_at=start)
    early, late = window("early"), window("late")
    early.start_at, early.end_at = start, end
    late.start_at, late.end_at = end, end + timedelta(hours=1)
    assert WindowInputParams(windows=[early, late])
    with pytest.raises(ValueError, match="ordered"):
        WindowInputParams(windows=[late, early])


def test_replay_clock_only_allows_its_owner_to_advance_and_rejects_invalid_time():
    clock = ReplayClock(START)
    with ThreadPoolExecutor(max_workers=1) as pool:
        assert pool.submit(clock.now).result() == START
        with pytest.raises(RuntimeError, match="replay driver"):
            pool.submit(clock.sleep, 1).result()
    assert clock.now() == START
    for seconds in (-1, float("inf"), float("nan")):
        with pytest.raises(ValueError):
            clock.sleep(seconds)
    with pytest.raises(ValueError):
        clock.advance_to(START - timedelta(seconds=1))
    with pytest.raises(ValueError):
        ReplayClock(datetime(2001, 1, 1))
    with pytest.raises(ValueError, match="aware"):
        DeadlineBudget(clock, datetime(2001, 1, 1))
    assert isinstance(clock, WindowClock)
