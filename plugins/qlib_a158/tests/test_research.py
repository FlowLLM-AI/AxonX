"""Exercise real CPU research, dependency selection and failure propagation."""

import argparse
import json
import math
from datetime import date, timedelta
from importlib import import_module
from pathlib import Path

import polars as pl
import pytest

from axonx.plugin.manifest import PluginManifest
from axonx.task.core.base import ChildTaskError
from axonx.task.models.identity import TaskState
from axonx.task.runtime.catalog import TaskCatalog
from axonx.task.runtime.executor import TaskExecutor
from axonx.task.storage.files import atomic_write_json
from axonx.task.storage.workspace import read_entry
from axonx_qlib_a158.etl import Alpha158Task
from axonx_qlib_a158.predict import LgbmPredictTask
from axonx_qlib_a158.research import Alpha158ResearchTask, ResearchInputParams
from axonx_qlib_a158.scripts.compare_parameters import run_comparison


@pytest.fixture
def catalog():
    registrations = []
    for plugin in ("qlib_a158", "qlib_factor", "qlib_strategy"):
        package = import_module("axonx_" + plugin)
        manifest = PluginManifest.parse((Path(package.__file__).parent / "plugin.yaml").read_text(), plugin)
        registrations.extend((name, target, plugin) for name, target in manifest.tasks.items())
    return TaskCatalog(registrations)


@pytest.fixture
def market(tmp_path):
    days, current = [], date(2024, 1, 1)
    while len(days) < 110:
        if current.weekday() < 5:
            days.append(current.strftime("%Y%m%d"))
        current += timedelta(days=1)
    root = tmp_path / "tushare"
    root.mkdir()
    codes = [f"{600000 + i:06d}.SH" for i in range(24)]
    pl.DataFrame({"cal_date": days, "is_open": [1] * len(days)}).write_parquet(root / "trade_cal.parquet")
    pl.DataFrame(
        {"ts_code": codes, "name": codes, "list_date": ["20100101"] * 24, "delist_date": [None] * 24},
        schema_overrides={"delist_date": pl.String},
    ).write_parquet(root / "stock_basic.parquet")
    pl.DataFrame(schema={key: pl.String for key in ("ts_code", "name", "start_date", "ann_date")}).write_parquet(
        root / "namechange.parquet"
    )
    prices = [10.0 + i for i in range(24)]
    for t, day in enumerate(days):
        partition = root / day[:4] / day
        partition.mkdir(parents=True)
        rows = []
        for i, code in enumerate(codes):
            previous = prices[i]
            close = previous * (1 + 0.004 * math.sin(t * 0.43 + i * 0.67) + 0.0002)
            volume = 100000.0 + 3000 * math.cos(t * 0.21 + i)
            rows.append(
                {
                    "ts_code": code,
                    "trade_date": day,
                    "open": previous,
                    "high": max(previous, close) * 1.005,
                    "low": min(previous, close) * 0.995,
                    "close": close,
                    "pre_close": previous,
                    "vol": volume,
                    "amount": volume * close / 10,
                }
            )
            prices[i] = close
        pl.DataFrame(rows).write_parquet(partition / "daily.parquet")
        pl.DataFrame({"ts_code": codes, "trade_date": [day] * 24, "adj_factor": [1.0] * 24}).write_parquet(
            partition / "adj_factor.parquet"
        )
    pl.DataFrame(
        {"index_code": ["000300.SH"] * 24, "trade_date": [days[0]] * 24, "con_code": codes, "weight": [100 / 24] * 24}
    ).write_parquet(root / days[0][:4] / days[0] / "index_weight.parquet")
    return days


def test_research_publishes_real_children_and_uses_explicit_prediction_etl(tmp_path, market, catalog):
    days = market
    executor = TaskExecutor(resolve_task=catalog.resolve)
    task = Alpha158ResearchTask(
        {
            "task_name": "research",
            "etl": {"start_date": days[60], "end_date": days[100]},
            "train": {
                "train_start": days[60],
                "train_end": days[85],
                "num_threads": 1,
                "num_boost_round": 8,
                "early_stopping_rounds": 3,
            },
            "predict": {"pred_end": days[95]},
            "backtest": {"top_ns": [5]},
            "analysis": {"minimum_daily_samples": 5},
        },
        workspace_path=tmp_path,
        reg_name="qlib_a158_research",
    )
    status = executor.execute(task)
    assert status.state == TaskState.SUCCEEDED
    assert [child.node_name for child in status.children] == ["etl", "analysis", "train", "predict", "backtest"]
    stages = task.output["stage_task_ids"]
    backtest = read_entry(tmp_path, stages["backtest"])
    assert backtest.output_params["universes"]["all"]["date_range"]["end"] == days[95]
    predict = read_entry(tmp_path, stages["predict"])
    assert predict.input_params["upstream_task_ids"] == [stages["train"], stages["etl"]]
    replacement = Alpha158Task(
        {"task_name": "new-data", "start_date": days[85], "end_date": days[100]},
        workspace_path=tmp_path,
        reg_name="qlib_a158_etl",
    )
    executor.execute(replacement)
    prediction = LgbmPredictTask(
        {
            "task_name": "new-data",
            "upstream_task_ids": [stages["train"], replacement.task_id],
            "pred_start": days[96],
            "pred_end": days[100],
        },
        workspace_path=tmp_path,
        reg_name="qlib_a158_predict",
    )
    executor.execute(prediction)
    assert prediction.output["protocol"]["market_upstream_task_id"] == replacement.task_id
    assert prediction.output["date_range"] == {"start": days[96], "end": days[100]}

    replacement.metadata.output_params["protocol"].pop("feature_family")
    atomic_write_json(replacement.metadata_path, replacement.metadata.model_dump(mode="json"))
    invalid = LgbmPredictTask(
        {"upstream_task_ids": [stages["train"], replacement.task_id], "pred_start": days[96]},
        workspace_path=tmp_path,
        reg_name="qlib_a158_predict",
    )
    with pytest.raises(ValueError, match="Incomplete feature protocol"):
        executor.execute(invalid)


def test_research_failure_records_child_and_stops_downstream(tmp_path, catalog):
    task = Alpha158ResearchTask({}, workspace_path=tmp_path, reg_name="qlib_a158_research")
    with pytest.raises(ChildTaskError):
        TaskExecutor(resolve_task=catalog.resolve).execute(task)
    status = read_entry(tmp_path, task.task_id)
    assert status.state == TaskState.FAILED
    assert len(status.children) == 1 and status.children[0].state == TaskState.FAILED


def test_research_owns_dependencies_and_derives_prediction_cutoff():
    assert ResearchInputParams(train={"train_end": "20250101"}).predict.pred_start == "20250101"
    with pytest.raises(ValueError, match="Research owns"):
        ResearchInputParams(train={"task_name": "other"})
    with pytest.raises(ValueError, match="pred_start"):
        ResearchInputParams(train={"train_end": "20250101"}, predict={"pred_start": "20240101"})
    assert "input_dir" in Alpha158Task.input_cls.model_json_schema()["properties"]


@pytest.mark.parametrize("backtest_registration", ["qlib_a158_backtest", "qlib_strategy_backtest"])
def test_factor_and_strategy_exchange_current_artifacts(tmp_path, market, catalog, backtest_registration):
    days = market
    executor = TaskExecutor(resolve_task=catalog.resolve)

    def run(registration, **inputs):
        task = catalog.resolve(registration)(
            {"task_name": "protocol", **inputs}, workspace_path=tmp_path, reg_name=registration
        )
        assert executor.execute(task).state == TaskState.SUCCEEDED
        return task

    etl = run("qlib_factor_etl", start_date=days[60], end_date=days[100])
    assert etl.output["protocol"]["feature_family"] == "qlib_factor"
    train = run(
        "qlib_factor_train",
        upstream_task_ids=[etl.task_id],
        train_start=days[60],
        train_end=days[85],
        context_groups=["mean", "variance"],
        num_threads=1,
        num_boost_round=8,
        early_stopping_rounds=3,
    )
    predict = run(
        "qlib_a158_predict", upstream_task_ids=[train.task_id, etl.task_id], pred_start=days[85], pred_end=days[95]
    )
    assert predict.output["protocol"]["market_upstream_task_id"] == etl.task_id
    backtest = run(backtest_registration, upstream_task_ids=[predict.task_id], top_ns=[5])
    assert backtest.output["universes"]["all"]["date_range"]["end"] == days[95]
    if backtest_registration == "qlib_strategy_backtest":
        assert backtest.output["protocol"]["strategy"] == "rank_retention"


@pytest.mark.parametrize("registration", ["qlib_a158_train", "qlib_a158_analysis"])
def test_feature_consumers_reject_incomplete_protocol(tmp_path, market, catalog, registration):
    executor = TaskExecutor(resolve_task=catalog.resolve)
    etl = Alpha158Task(
        {"start_date": market[60], "end_date": market[100]}, workspace_path=tmp_path, reg_name="qlib_a158_etl"
    )
    executor.execute(etl)
    etl.metadata.output_params["protocol"].pop("feature_family")
    atomic_write_json(etl.metadata_path, etl.metadata.model_dump(mode="json"))
    consumer = catalog.resolve(registration)(
        {"upstream_task_ids": [etl.task_id]}, workspace_path=tmp_path, reg_name=registration
    )
    with pytest.raises(ValueError, match="Incomplete feature protocol"):
        executor.execute(consumer)
    assert read_entry(tmp_path, consumer.task_id).state == TaskState.FAILED


def test_parameter_comparison_records_current_execution_provenance(tmp_path, market):
    etl = Alpha158Task(
        {"start_date": market[60], "end_date": market[100]}, workspace_path=tmp_path, reg_name="qlib_a158_etl"
    )
    TaskExecutor().execute(etl)
    result = run_comparison(
        argparse.Namespace(
            workspace_dir=tmp_path,
            etl_task=etl.task_id,
            labels=["rank", "csz"],
            train_start=market[60],
            train_end=market[85],
            pred_start=market[85],
            pred_end=market[95],
            num_threads=1,
            num_boost_round=4,
            top_ns=[5],
            buy_cost_rate=0.0005,
            sell_cost_rate=0.0015,
        )
    )
    output = Path(result["output_dir"])
    saved = json.loads((output / "comparison.json").read_text())
    assert saved["etl_started_at"] == etl.metadata.model_dump(mode="json", include={"started_at"})["started_at"]
    assert set(saved["presets"]) == {"rank_axonx", "rank_qlib", "csz_axonx", "csz_qlib"}
    for record in saved["presets"].values():
        for stage, task_id in record["tasks"].items():
            metadata = read_entry(tmp_path, task_id)
            assert metadata.exit_code == 0
            assert record["started_at"][stage] == metadata.model_dump(mode="json", include={"started_at"})["started_at"]
    summary = pl.read_csv(output / "summary.csv")
    assert set(summary["universe"]) == {"all", "hs300"}
    assert set(summary["label"]) == {"rank", "csz"}
