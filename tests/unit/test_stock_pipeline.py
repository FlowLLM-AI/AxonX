"""Actual ETL/train/predict/backtest lifecycle for all three research layers."""

from datetime import date, timedelta
from pathlib import Path

import polars as pl
import pytest

from axonx.enums import TaskState
from axonx.task.runtime.runner import TaskRunner
from axonx.task.storage import artifact_path, read_metadata


def raw_data(root):
    dates = []
    day = date(2025, 1, 2)
    while len(dates) < 85:
        if day.weekday() < 5:
            dates.append(day.strftime("%Y%m%d"))
        day += timedelta(days=1)
    codes = [f"00000{i}.SZ" for i in range(1, 7)]
    root.mkdir()
    pl.DataFrame({"cal_date": dates, "is_open": [1] * len(dates)}).write_parquet(root / "trade_cal.parquet")
    pl.DataFrame(
        {"ts_code": codes, "name": codes, "list_date": ["20000101"] * 6, "delist_date": [None] * 6}
    ).write_parquet(root / "stock_basic.parquet")
    pl.DataFrame(
        {"ts_code": codes, "name": codes, "ann_date": ["20000101"] * 6, "start_date": ["20000101"] * 6}
    ).write_parquet(root / "namechange.parquet")
    for i, day in enumerate(dates):
        rows = []
        for j, code in enumerate(codes):
            price = 10 + j + i * 0.01 + ((i + j) % 7) * 0.001
            rows.append(
                {
                    "ts_code": code,
                    "trade_date": day,
                    "open": price - 0.005,
                    "high": price + 0.01,
                    "low": price - 0.01,
                    "close": price,
                    "pre_close": price - 0.01,
                    "vol": 1000.0 + j,
                    "amount": price * (1000 + j),
                }
            )
        folder = root / day[:4] / day
        folder.mkdir(parents=True)
        pl.DataFrame(rows).write_parquet(folder / "daily.parquet")
        pl.DataFrame({"ts_code": codes, "trade_date": [day] * 6, "adj_factor": [1.0] * 6}).write_parquet(
            folder / "adj_factor.parquet"
        )
    return dates


@pytest.mark.parametrize(
    "layer,parameter_preset", [("baseline", "axonx"), ("factor", "axonx"), ("strategy", "axonx"), ("baseline", "qlib")]
)
def test_complete_new_artifact_pipeline(tmp_path, layer, parameter_preset):
    pytest.importorskip("lightgbm")
    if layer != "baseline":
        from axonx_qlib_factor.etl import Alpha158Task
        from axonx_qlib_factor.train import LgbmTrainTask
        from axonx_qlib_a158.predict import LgbmPredictTask
        from axonx_qlib_a158.backtest import Alpha158BacktestTask
        from axonx_qlib_a158.analysis import FactorAnalysisTask
    else:
        from axonx_qlib_a158.etl import Alpha158Task
        from axonx_qlib_a158.train import LgbmTrainTask
        from axonx_qlib_a158.predict import LgbmPredictTask
        from axonx_qlib_a158.backtest import Alpha158BacktestTask
        from axonx_qlib_a158.analysis import FactorAnalysisTask
    if layer == "strategy":
        from axonx_qlib_strategy.backtest import StrategyBacktestTask

        backtest_cls = StrategyBacktestTask
    else:
        backtest_cls = Alpha158BacktestTask
    raw = tmp_path / "raw"
    dates = raw_data(raw)
    # Irrelevant old history may be incomplete; retain exactly the required rolling history.
    old = raw / "2014" / "20140102"
    old.mkdir(parents=True)
    pl.read_parquet(raw / dates[0][:4] / dates[0] / "daily.parquet").with_columns(
        pl.lit("20140102").alias("trade_date")
    ).write_parquet(old / "daily.parquet")
    pl.DataFrame({"ts_code": ["000001.SZ"], "trade_date": ["20140102"], "adj_factor": [0.0]}).write_parquet(
        old / "adj_factor.parquet"
    )
    workspace = tmp_path / "workspace"

    def run(cls, name, **params):
        task = cls(params, workspace_path=workspace, reg_name=name)
        original_inputs = task.input_params.model_dump(mode="json")
        status = TaskRunner().run(task)
        assert task.input_params.model_dump(mode="json") == original_inputs
        assert status.state == TaskState.SUCCEEDED, status.error
        return task, status.result

    states = tmp_path / "market_status.parquet"
    pl.DataFrame(
        {"trade_date": [dates[64]], "trade_time": ["1500"], "ts_code": ["000001.SZ"], "market_status": ["suspended"]}
    ).write_parquet(states)
    etl, output = run(Alpha158Task, "etl", input_dir=raw, start_date=dates[60], market_status_file=states)
    assert etl.state["daily_files"][0].parent.name == dates[0]
    metadata = read_metadata(etl.metadata_path)
    assert {"dataset", "labels", "market", "calendar"} <= set(output["artifacts"])
    dataset = pl.read_parquet(output["output_file"])
    assert not any(c.startswith("label_") or c in {"exit_date", "exit_delayed"} for c in dataset.columns)
    suspended = dataset.filter((pl.col("trade_date") == dates[64]) & (pl.col("ts_code") == "000001.SZ"))
    assert suspended["is_model_candidate"].item()
    assert not suspended["is_buyable_at_signal"].item()
    assert not suspended["is_buyable"].item()
    labels = pl.read_parquet(artifact_path(etl.task_dir, metadata, "labels"))
    assert (
        labels.filter((pl.col("trade_date") == dates[64]) & (pl.col("ts_code") == "000001.SZ"))["label_status"].item()
        == "suspended"
    )
    assert labels.filter(pl.col("trade_date") == dates[-1])["label_return"].null_count() == 6
    train, trained = run(
        LgbmTrainTask,
        "train",
        source_tasks=etl.task_id,
        parameter_preset=parameter_preset,
        train_start=dates[60],
        train_end=dates[75],
        trim_tail=0.0,
        num_boost_round=5,
        early_stopping_rounds=2,
        min_data_in_leaf=2,
        num_threads=1,
    )
    assert train.state["frame"]["label_target_date"].max() < dates[75]
    assert train.state["tuning_train"]["label_target_date"].max() < train.state["validation_start"]
    predict, predicted = run(LgbmPredictTask, "predict", source_tasks=train.task_id, pred_start=dates[75])
    assert trained["model_files"] == {"model": str(train.state["model_path"])}
    assert predicted["score_columns"] == {"model": "pred"}
    assert trained["model_files"].keys() == predicted["score_columns"].keys()
    predictions = pl.read_parquet(predicted["predictions_file"])
    assert set(predicted["score_columns"].values()) <= set(predictions.columns)
    assert "actual_return" not in predictions.columns
    stats = predicted["statistics"]
    assert stats["days"] == 10 and stats["symbols"] == 6
    assert stats["pred"]["mean"] == pytest.approx(predictions["pred"].mean())
    assert (
        stats["candidate_rows"]
        == predictions.filter(pl.col("is_buyable_at_signal") & pl.col("is_model_candidate")).height
    )
    assert "valid_return_rows" not in stats
    _, result = run(
        backtest_cls,
        "backtest",
        source_tasks=predict.task_id,
        top_ns=[1, 3],
        buy_cost_rate=0.0005 if parameter_preset == "qlib" else 0.0,
        sell_cost_rate=0.0015 if parameter_preset == "qlib" else 0.0,
        **({"minimum_holding_days": 0} if layer == "strategy" else {}),
    )
    if parameter_preset == "qlib":
        orders = pl.read_parquet(result["orders_file"]).filter(pl.col("status") == "filled")
        for row in orders.iter_rows(named=True):
            rate = 0.0005 if row["side"] == "buy" else 0.0015
            assert row["fee"] == pytest.approx(row["notional"] * rate)
        assert result["protocol"]["settings"]["buy_cost_rate"] == 0.0005
    assert result["dimensions"]["top_ns"] == [1, 3]
    assert result["days"] == 10 and result["evaluation_status"] == "done"
    assert pl.read_parquet(result["positions_file"]).height > 0
    assert pl.read_parquet(result["trades_file"]).height > 0
    _, analysis = run(FactorAnalysisTask, "factor", source_tasks=etl.task_id, minimum_daily_samples=3, quantiles=3)
    assert Path(analysis["result_file"]).is_file()
