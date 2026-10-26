"""Exercise Task contracts at input, persistence and event boundaries."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from axonx.task.builtins.stock.models import STOCK_REPORT_ARTIFACTS, StockOnlineReport, StockReportSettings
from axonx.task.models.artifacts import ArtifactRecord, PredictionProtocol, task_protocol
from axonx.task.models.base import normalize_yyyymmdd
from axonx.task.models.events import TASK_EVENT_ADAPTER, LogChunk, LogEvent, ProgressEvent
from axonx.task.models.identity import TaskType, task_type_from_id, validate_task_names
from axonx.task.models.lifecycle import TaskMetadata, TaskSource, TaskStepStatus
from axonx.task.models.params import BaseInputParams, BasePredictOutputParams
from axonx.task.models.query import TaskGraphEdge
from axonx.task.models.reports import BacktestDimensions, OnlineCommit, TrainingCurve, WindowResult


@pytest.mark.parametrize("name", ["", "bad_name", "a/b", "a#b", "a" * 33, "name\n"])
def test_task_names_share_input_identity_and_sync_rules(name):
    if name:
        with pytest.raises(ValueError):
            BaseInputParams(task_name=name)
    else:
        assert BaseInputParams(task_name=name).task_name is None
    with pytest.raises(ValueError):
        task_type_from_id(f"train#model#{name}")
    with pytest.raises(ValueError):
        validate_task_names([name])


def test_sources_normalize_and_assignment_still_validates():
    params = BaseInputParams(source_tasks=" etl#dataset#daily, train#model#baseline ")
    assert params.source_tasks == "etl#dataset#daily,train#model#baseline"
    assert params.source_task(TaskType.TRAIN) == "train#model#baseline"
    with pytest.raises(ValidationError, match="duplicate"):
        params.source_tasks = "etl#dataset#daily,etl#dataset#daily"
    with pytest.raises(ValidationError):
        params.task_name = "bad_name"
    assert params.task_name is None


@pytest.mark.parametrize("value", [20240229, "20240229"])
def test_date_normalization_accepts_real_leap_days(value):
    assert normalize_yyyymmdd(value) == "20240229"


@pytest.mark.parametrize("value", ["20230229", "20241301", "2024011", "2024-01-01", "", None])
def test_date_normalization_rejects_invalid_dates(value):
    with pytest.raises(ValueError):
        normalize_yyyymmdd(value)


@pytest.fixture
def prediction_protocol():
    return task_protocol(
        TaskType.PREDICT,
        model_identity={"model": "revision"},
        dates=["20240229"],
        score_columns={"model": "score"},
        predictions_revision="10:20",
        plugin_settings={"feature": "close"},
    )


@pytest.mark.parametrize("dates", [["20230229"], ["20240301", "20240229"], ["20240229", "20240229"]])
def test_prediction_dates_are_valid_sorted_and_unique(prediction_protocol, dates):
    with pytest.raises(ValidationError):
        PredictionProtocol.model_validate({**prediction_protocol, "dates": dates})


def test_protocol_extensions_survive_roundtrip(prediction_protocol):
    protocol = PredictionProtocol.model_validate(prediction_protocol)
    assert protocol.model_dump(mode="json") == prediction_protocol
    output = BasePredictOutputParams(
        rows=1, date_range={"start": "20240229", "end": "20240229"}, protocol=protocol.model_dump()
    )
    assert output.model_dump(mode="json")["protocol"] == prediction_protocol


@pytest.mark.parametrize("changes", [{"task_type": "inference"}, {"version": True}, {"dates": ["20230229"]}])
def test_prediction_results_validate_their_protocol(prediction_protocol, changes):
    with pytest.raises(ValidationError):
        BasePredictOutputParams(rows=1, date_range={}, protocol={**prediction_protocol, **changes})


@pytest.mark.parametrize("path", ["/absolute", "../outside", "a/../b", "a//b", "a\\b"])
def test_artifact_references_reject_unsafe_paths(path):
    with pytest.raises(ValidationError):
        ArtifactRecord(path=path, size=0, revision="0:1")


def test_metadata_is_closed_even_though_its_protocol_is_extensible():
    now = datetime.now(UTC)
    values = {
        "version": 1,
        "task_type": TaskType.TRAIN,
        "task_id": "train#model#daily",
        "pid": 1,
        "machine_id": "machine",
        "process_started_at": now,
        "started_at": now,
    }
    metadata = TaskMetadata(**values)
    assert TaskMetadata.model_validate_json(metadata.model_dump_json()) == metadata
    attempts = [
        {"node_name": "child", "attempt": attempt, "task": "model", "task_id": "train#model#child"}
        for attempt in (1, 2)
    ]
    attempts.append({"node_name": "invalid", "attempt": 1, "task": "model"})
    metadata = TaskMetadata(**values, children=attempts)
    assert [child.attempt for child in metadata.current_children()] == [2]
    assert len(metadata.children) == 3
    with pytest.raises(ValidationError, match="extra_forbidden"):
        TaskMetadata(**values, plugin_setting=True)
    source = TaskSource(kind="exec")
    with pytest.raises(ValidationError, match="frozen_instance"):
        source.kind = "unknown"


def test_events_roundtrip_and_query_aliases_remain_stable():
    step = TaskStepStatus(name="train", percentage=50, completed=1, total=2)
    progress = ProgressEvent.from_status(step)
    log = LogEvent.from_chunk(LogChunk(content="training", next_offset=8, file_size=8))
    for event in (progress, log):
        assert TASK_EVENT_ADAPTER.validate_json(event.model_dump_json()) == event
    with pytest.raises(ValidationError):
        TASK_EVENT_ADAPTER.validate_python({"kind": "unknown"})
    edge = TaskGraphEdge(from_="source", to="target")
    assert edge.model_dump() == {"from": "source", "to": "target"}


@pytest.mark.parametrize(
    "values",
    [
        {"x": ["1"], "y_left": {"loss": []}},
        {"x": ["1"], "y_left": {"loss": [float("nan")]}},
        {"x": ["1"], "y_left": {"loss": [1]}, "y_right": {"loss": [2]}},
    ],
)
def test_training_curves_reject_misaligned_nonfinite_or_ambiguous_series(values):
    with pytest.raises(ValidationError):
        TrainingCurve(**values)


@pytest.mark.parametrize("top_ns, detail", [([], 1), ([0], 1), ([1, 1], 1), ([1], 0)])
def test_report_dimensions_validate_for_every_report(top_ns, detail):
    with pytest.raises(ValidationError):
        BacktestDimensions(top_ns=top_ns, holding_detail_top_n=detail, benchmarks=[])


def test_online_dates_share_calendar_validation():
    now = datetime.now(UTC)
    values = {
        "commit_id": "a" * 32,
        "task_id": "inference#model#daily",
        "started_at": now,
        "trade_date": "20240229",
        "trade_time": "0930",
        "revision": 1,
        "committed_at": now,
        "model_identity": {"model": "revision"},
        "protocol": task_protocol(TaskType.INFERENCE),
        "artifacts": {"predictions": ArtifactRecord(path="predictions.parquet", size=0, revision="0:1")},
    }
    assert OnlineCommit(**values).trade_date == "20240229"
    with pytest.raises(ValidationError):
        OnlineCommit(**{**values, "trade_date": "20230229"})
    with pytest.raises(ValidationError, match="settings must be an object"):
        OnlineCommit(**{**values, "protocol": task_protocol(TaskType.INFERENCE, report=1)})
    settings = {
        "signals_format": "stock-signals-v1",
        "strategy_identity": "a" * 64,
        "dimensions": {"top_ns": [1], "holding_detail_top_n": 1, "benchmarks": []},
        "date_range": {"start": "20240228", "end": "20240229"},
        "portfolio": {},
        "score_selection": {},
        "evaluation_status": "done",
    }
    assert StockReportSettings(**settings).date_range == settings["date_range"]
    with pytest.raises(ValidationError):
        StockReportSettings(**settings, missing_dates=["20240301"])


@pytest.mark.parametrize("problem", [None, "format", "targets", "missing"])
def test_stock_publication_rules_are_enforced_by_the_stock_contract(problem):
    now = datetime.now(UTC)
    record = ArtifactRecord(path="data.parquet", size=0, revision="0:1")
    settings = {
        "signals_format": "stock-signals-v1" if problem != "format" else "custom-signals-v1",
        "strategy_identity": "a" * 64,
        "dimensions": {"top_ns": [1], "holding_detail_top_n": 1, "benchmarks": []},
        "date_range": {"start": "20240229", "end": "20240229"},
        "portfolio": {},
        "score_selection": {},
        "evaluation_status": "done",
    }
    artifacts = {name: record for name in STOCK_REPORT_ARTIFACTS}
    if problem == "targets":
        artifacts["targets"] = record
    if problem == "missing":
        artifacts.pop("calendar")
    commit = OnlineCommit(
        commit_id="a" * 32,
        task_id="inference#model#daily",
        started_at=now,
        trade_date="20240229",
        trade_time="0930",
        revision=1,
        committed_at=now,
        model_identity={"model": "revision"},
        protocol=task_protocol(TaskType.INFERENCE, report=settings),
        artifacts=artifacts,
    )
    # Generic online publication permits business-specific roles and formats.
    assert OnlineCommit.model_validate_json(commit.model_dump_json()) == commit
    if problem is None:
        assert StockOnlineReport(commit=commit).commit == commit
    else:
        with pytest.raises(ValidationError):
            StockOnlineReport(commit=commit)


@pytest.mark.parametrize(
    "changes",
    [
        {"commit_id": "a" * 32},
        {"committed_at": datetime.now(UTC)},
        {"status": "failed", "commit_id": "a" * 32, "committed_at": datetime.now(UTC)},
        {"elapsed_seconds": float("inf")},
    ],
)
def test_window_results_reject_partial_commits_and_nonfinite_elapsed_time(changes):
    with pytest.raises(ValidationError):
        WindowResult(**{"key": "open", "status": "done", **changes})
