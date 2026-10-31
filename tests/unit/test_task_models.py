"""Exercise Task contracts at input, persistence and event boundaries."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from axonx.task.builtins.stock.models import (
    STOCK_REPORT_ARTIFACTS,
    StockOnlineReport,
    StockReportSettings,
    portfolio_key,
)
from axonx.task.models.artifacts import (
    ArtifactRecord,
    PredictionProtocol,
    task_protocol,
)
from axonx.task.models.base import normalize_yyyymmdd
from axonx.task.models.events import (
    TASK_EVENT_ADAPTER,
    LogChunk,
    LogEvent,
    ProgressEvent,
)
from axonx.task.models.identity import (
    TaskType,
    task_type_from_id,
    validate_task_ids,
    validate_task_names,
)
from axonx.task.models.lifecycle import TaskMetadata, TaskStepStatus
from axonx.task.models.params import BaseInputParams, BasePredictOutputParams
from axonx.task.models.query import TaskGraphEdge
from axonx.task.models.reports import (
    BacktestDimensions,
    OnlineCommit,
    TrainingCurve,
    WindowResult,
)


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


@pytest.mark.parametrize(
    "task_id",
    [
        None,
        1,
        "/train#model#daily",
        "train#../model#daily",
        "train#model#../daily",
        "train#model#daily/",
        "train#model\\other#daily",
        "train#model#daily#extra",
        "unknown#model#daily",
    ],
)
def test_task_id_grammar_rejects_paths_and_noncanonical_ids(task_id):
    with pytest.raises(ValueError):
        task_type_from_id(task_id)


@pytest.mark.parametrize("validate", [validate_task_names, validate_task_ids])
@pytest.mark.parametrize("value", ["daily", {"daily": True}, 1])
def test_task_filters_reject_scalars_and_mappings(validate, value):
    with pytest.raises(ValueError, match="must be a list"):
        validate(value)


def test_upstream_ids_and_assignment_are_validated():
    params = BaseInputParams(upstream_task_ids=["etl#dataset#daily", "train#model#baseline"])
    assert params.upstream_task_ids == ["etl#dataset#daily", "train#model#baseline"]
    assert params.upstream_task_id(TaskType.TRAIN) == "train#model#baseline"
    with pytest.raises(ValidationError, match="duplicate"):
        params.upstream_task_ids = ["etl#dataset#daily", "etl#dataset#daily"]
    with pytest.raises(ValidationError):
        params.task_name = "bad_name"
    assert params.task_name is None


@pytest.mark.parametrize("field", ["source_tasks", "parent_task_id", "children"])
def test_upstream_input_does_not_accept_retired_names_or_invocation_ownership(field):
    with pytest.raises(ValidationError, match="extra_forbidden"):
        BaseInputParams(**{field: []})


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
        score_columns={"model": "score"},
        windows=[
            {
                "prediction_start": "20240229",
                "prediction_end_exclusive": "20240301",
                "models": {"model": "final-model"},
                "model_identity": {"model": "revision"},
            }
        ],
        plugin_settings={"feature": "close"},
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"prediction_start": "20230229"},
        {"prediction_start": "20240301"},
        {"prediction_end_exclusive": "20240228"},
        {"models": {"other": "final-model"}},
    ],
)
def test_prediction_windows_validate_dates_and_members(prediction_protocol, changes):
    with pytest.raises(ValidationError):
        PredictionProtocol.model_validate(
            {
                **prediction_protocol,
                "windows": [{**prediction_protocol["windows"][0], **changes}],
            }
        )


def test_prediction_windows_route_half_open_intervals(prediction_protocol):
    first = prediction_protocol["windows"][0]
    second = {
        **first,
        "prediction_start": "20240301",
        "prediction_end_exclusive": "20240401",
        "model_identity": {"model": "next-revision"},
    }
    protocol = PredictionProtocol.model_validate({**prediction_protocol, "windows": [first, second]})
    assert protocol.window_for(20240229).model_identity == {"model": "revision"}
    assert protocol.window_for("20240301").model_identity == {"model": "next-revision"}
    with pytest.raises(ValueError, match="No prediction model window"):
        protocol.window_for("20240401")
    for windows in ([second, first], [first, first]):
        with pytest.raises(ValidationError, match="ordered and non-overlapping"):
            PredictionProtocol.model_validate({**prediction_protocol, "windows": windows})


def test_protocol_extensions_survive_roundtrip(prediction_protocol):
    protocol = PredictionProtocol.model_validate(prediction_protocol)
    assert protocol.model_dump(mode="json") == prediction_protocol
    output = BasePredictOutputParams(
        rows=1,
        date_range={"start": "20240229", "end": "20240229"},
        protocol=protocol.model_dump(),
        artifacts={"predictions": ArtifactRecord(path="predictions.parquet", size=0, revision="0:1")},
    )
    assert output.model_dump(mode="json")["protocol"] == prediction_protocol


@pytest.mark.parametrize("changes", [{"task_type": "inference"}, {"version": True}, {"windows": []}])
def test_prediction_results_validate_their_protocol(prediction_protocol, changes):
    with pytest.raises(ValidationError):
        BasePredictOutputParams(
            rows=1,
            date_range={},
            protocol={**prediction_protocol, **changes},
            artifacts={"predictions": ArtifactRecord(path="predictions.parquet", size=0, revision="0:1")},
        )


@pytest.mark.parametrize("roles", [[], ["other"], ["predictions", "protocol"]])
def test_prediction_output_requires_one_prediction_artifact(prediction_protocol, roles):
    with pytest.raises(ValidationError):
        BasePredictOutputParams(
            rows=1,
            date_range={},
            protocol=prediction_protocol,
            artifacts={name: ArtifactRecord(path="predictions.parquet", size=0, revision="0:1") for name in roles},
        )


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
        {
            "node_name": "child",
            "attempt": attempt,
            "reg_name": "model",
            "child_task_id": "train#model#child",
        }
        for attempt in (1, 2)
    ]
    attempts.append({"node_name": "invalid", "attempt": 1, "reg_name": "model"})
    metadata = TaskMetadata(**values, children=attempts)
    assert [child.attempt for child in metadata.current_children()] == [2]
    assert len(metadata.children) == 3
    with pytest.raises(ValidationError, match="extra_forbidden"):
        TaskMetadata(**values, plugin_setting=True)


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


def test_portfolio_series_survive_ensemble_rolls_without_changing_recorded_identities():
    first = {"top_n": 10, "score_selection": {"method": "mean", "seeds": [0]}}
    rolled = {"top_n": 10, "score_selection": {"method": "mean", "seeds": [42]}}
    assert portfolio_key(first) == portfolio_key(rolled)
    assert first["score_selection"]["seeds"] == [0]
    first["score_selection"]["method"] = rolled["score_selection"]["method"] = "seed"
    assert portfolio_key(first) != portfolio_key(rolled)


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
        "signals_format": "stock-signals-v3",
        "score_column": "pred",
        "strategy_identity": "a" * 64,
        "dimensions": {"top_ns": [1], "holding_detail_top_n": 1, "benchmarks": []},
        "date_range": {"start": "20240228", "end": "20240229"},
        "portfolio": {},
        "portfolios": {portfolio_key({"top_n": 1}): {"top_n": 1}},
        "score_selection": {},
        "evaluation_status": "done",
    }
    assert StockReportSettings(**settings).date_range == settings["date_range"]
    with pytest.raises(ValidationError):
        StockReportSettings(**settings, missing_dates=["20240301"])


@pytest.mark.parametrize("problem", [None, "format", "date", "missing"])
def test_stock_publication_rules_are_enforced_by_the_stock_contract(problem):
    now = datetime.now(UTC)
    record = ArtifactRecord(path="data.parquet", size=0, revision="0:1")
    settings = {
        "signals_format": ("stock-signals-v3" if problem != "format" else "custom-signals-v1"),
        "score_column": "pred",
        "strategy_identity": "a" * 64,
        "dimensions": {"top_ns": [1], "holding_detail_top_n": 1, "benchmarks": []},
        "date_range": {"start": "20240229", "end": "20240229"},
        "portfolio": {},
        "portfolios": {portfolio_key({"top_n": 1}): {"top_n": 1}},
        "score_selection": {},
        "evaluation_status": "done",
    }
    artifacts = {name: record for name in STOCK_REPORT_ARTIFACTS}
    if problem == "date":
        settings["date_range"]["end"] = "20240301"
    if problem == "missing":
        artifacts.pop("rankings")
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


def test_training_model_groups_route_boundaries_and_future_dates():
    from axonx.task.models.params import BaseTrainOutputParams

    def group(start, stop=None):
        return {
            "train_start": 20220101,
            "train_end_exclusive": start,
            "use_from": start,
            "use_to": stop,
            "models": {
                "seed_7": {
                    "model": {"random_seed": 7},
                    "state": "succeeded",
                    "model_artifact": "weights",
                }
            },
        }

    params = {
        "feature_protocol": task_protocol(TaskType.ETL),
        "model_groups": [group(20230101, 20230701), group(20230701)],
        "artifacts": {"weights": {"path": "models/latest.pt", "size": 1, "revision": "1:1"}},
    }
    output = BaseTrainOutputParams(**params)
    assert output.select_group(20230630).use_from == "20230101"
    assert output.select_group(20230701).use_from == "20230701"
    assert output.select_group(20990101).use_from == "20230701"
    assert len(output.select_groups(20230630, 20230701)) == 2
    for start, end in (
        (20221231, 20230101),
        (20230701, 20230101),
        ("20230230", 20230701),
    ):
        with pytest.raises(ValueError):
            output.select_groups(start, end)
    output.model_groups[-1].models["seed_7"].state = "failed"
    with pytest.raises(ValueError, match="No completed model group"):
        output.select_group(20230701)
    with pytest.raises(ValueError, match="unregistered artifact"):
        BaseTrainOutputParams(**(params | {"artifacts": {}}))
    for groups in (
        [group(20230101), group(20230701)],
        [group(20230701), group(20230101)],
    ):
        with pytest.raises(ValueError, match="ordered and non-overlapping"):
            BaseTrainOutputParams(**(params | {"model_groups": groups}))
    output = BaseTrainOutputParams(**(params | {"model_groups": [group(20230101, 20230601), group(20230701)]}))
    with pytest.raises(ValueError, match="No completed model group"):
        output.select_groups(20230101, 20230701)
    assert output.select_group(20230701).use_from == "20230701"
