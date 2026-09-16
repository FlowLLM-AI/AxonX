import json
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from axonx.task.alpha158 import (
    Alpha158BacktestTask,
    FactorAnalysisTask,
    LgbmPredictionTask,
    LgbmTrainingConfig,
    LgbmTrainingTask,
)
from axonx.task.alpha158.internal.artifacts import artifact_path
from axonx.task.alpha158.internal.modeling import feature_matrix


def _etl_fixture(workspace: Path) -> str:
    task_id = "etl#fixture"
    output_dir = workspace / "etl" / task_id
    output_dir.mkdir(parents=True)
    features = ("f_alpha158_signal", "f_alpha158_inverse", "f_alpha158_wave")
    dates = [
        *(f"202212{day:02d}" for day in range(1, 21)),
        *(f"202301{day:02d}" for day in range(2, 7)),
    ]
    rows = []
    for date_index, trade_date in enumerate(dates):
        for stock_index in range(40):
            signal = (stock_index - 19.5) / 20
            row = {
                "trade_date": trade_date,
                "ts_code": f"{stock_index:06d}.SZ",
                "name": f"股票{stock_index}",
                "list_date": "20200101",
                "delist_date": None,
                "is_st": False,
                "is_delisting": False,
                "is_limit_up": False,
                "is_limit_down": False,
                "is_insufficient_history": False,
                "is_buyable": stock_index != 0,
                features[0]: signal,
                features[1]: -signal,
                features[2]: np.sin(stock_index + date_index),
                "index_weight_hs300": 1 / 40,
            }
            for horizon in range(1, 6):
                label = signal * 0.01 * horizon + date_index * 0.00001
                row[f"label_{horizon}d"] = label
                row[f"label_{horizon}d_csz"] = signal
                row[f"label_{horizon}d_rank"] = (stock_index + 1) / 40
                row[f"label_{horizon}d_is_valid"] = date_index < len(dates) - horizon
            rows.append(row)
    dataset = output_dir / "alpha158.parquet"
    pl.DataFrame(rows).write_parquet(dataset)
    metadata = {
        "task_name": "alpha158_etl",
        "task_id": task_id,
        "task_type": "etl",
        "feature_columns": list(features),
        "artifacts": {"dataset": "alpha158.parquet"},
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    return task_id


def test_training_defaults():
    config = LgbmTrainingConfig(etl_task_id="etl#fixture")

    assert config.train_start == "20150101"
    assert config.train_end == "20230101"
    assert config.label_column == "label_1d_rank"
    assert config.trim_tail == pytest.approx(0.025)


def test_feature_matrix_preserves_feature_order_and_missing_values():
    """Training and prediction must apply the same finite-value conversion."""
    frame = pl.DataFrame({"first": [1.0, float("inf"), None], "second": [2.0, 3.0, 4.0]})

    matrix = feature_matrix(frame, ("second", "first"))

    assert matrix.shape == (3, 2)
    assert matrix[:, 0].tolist() == [2.0, 3.0, 4.0]
    assert matrix[0, 1] == pytest.approx(1.0)
    assert np.isnan(matrix[1:, 1]).all()


@pytest.mark.parametrize("artifact", ["../outside.parquet", "/tmp/outside.parquet"])
def test_artifact_path_stays_inside_task_directory(tmp_path, artifact):
    with pytest.raises(ValueError, match="任务目录"):
        artifact_path(tmp_path / "etl#fixture", {"artifacts": {"dataset": artifact}}, "dataset")


def test_task_id_chained_alpha158_pipeline(tmp_path):
    etl_task_id = _etl_fixture(tmp_path)

    analysis = FactorAnalysisTask(
        {"etl_task_id": etl_task_id, "minimum_daily_samples": 10, "quantiles": 5},
        workspace_path=tmp_path,
    )
    analysis_output = analysis.execute()
    factor_result = pl.read_csv(analysis_output["result_file"])
    assert factor_result.height == 15
    signal = factor_result.filter(
        (pl.col("factor") == "f_alpha158_signal") & (pl.col("label") == "label_1d"),
    )
    assert signal["rankic_mean"].item() == pytest.approx(1.0)
    assert signal["quantile_monotonicity"].item() == pytest.approx(1.0)
    assert Path(analysis_output["metadata_file"]).is_file()

    training = LgbmTrainingTask(
        {
            "etl_task_id": etl_task_id,
            "train_start": "20221201",
            "train_end": "20230101",
            "num_boost_round": 30,
            "early_stopping_rounds": 5,
            "min_data_in_leaf": 5,
            "num_threads": 1,
        },
        workspace_path=tmp_path,
    )
    training_output = training.execute()
    assert training_output["train_rows"] < 20 * 40
    assert training_output["best_iteration"] >= 1
    assert Path(training_output["model_file"]).is_file()
    training_metadata = json.loads(Path(training_output["metadata_file"]).read_text())
    assert training_metadata["protocol"]["label_column"] == "label_1d_rank"
    assert training_metadata["protocol"]["daily_trim_tail"] == pytest.approx(0.025)

    prediction = LgbmPredictionTask(
        {"training_task_id": training.task_id, "pred_start": "20230102"},
        workspace_path=tmp_path,
    )
    assert prediction.task_id.startswith("predict#")
    prediction_output = prediction.execute()
    predictions = pl.read_parquet(prediction_output["predictions_file"])
    assert predictions.height == 5 * 40
    assert predictions.filter(~pl.col("is_buyable")).height == 5
    assert predictions.columns == [
        "trade_date",
        "ts_code",
        "pred",
        "actual_return",
        "label_valid",
        "name",
        "is_buyable",
        "index_weight_hs300",
    ]
    prediction_metadata = json.loads(Path(prediction_output["metadata_file"]).read_text())
    assert prediction_metadata["protocol"]["actual_return_column"] == "label_1d"
    assert prediction_metadata["protocol"]["cross_section_filter"] == "none"

    backtest = Alpha158BacktestTask(
        {"prediction_task_id": prediction.task_id},
        workspace_path=tmp_path,
    )
    backtest_output = backtest.execute()
    daily = pl.read_parquet(backtest_output["daily_file"])
    summary = pl.read_parquet(backtest_output["summary_file"])
    assert daily["rank_ic"].min() > 0.9
    assert daily["candidate_count"].max() == 39
    assert daily["top30_holdings"].list.len().max() == 30
    assert "000000.SZ" not in daily["top30_holdings"].explode(empty_as_null=True).struct.field("ts_code").to_list()
    assert daily["top1_turnover"][0] == 0
    assert daily.select(pl.col("top30_ndcg").is_between(0, 1).all()).item()
    expected_universe = (
        predictions.filter(pl.col("label_valid"))
        .group_by("trade_date")
        .agg(
            pl.col("actual_return").mean().alias("expected"),
        )
    )
    benchmark = daily.join(expected_universe, on="trade_date")
    assert benchmark.select(
        (pl.col("benchmark_universe_return") - pl.col("expected")).abs().max(),
    ).item() == pytest.approx(0)
    assert set(summary["period_type"]) == {"overall", "year", "quarter", "month"}
    assert "top30_information_ratio_hs300" in summary.columns
    assert "top30_ndcg" in daily.columns
    assert Path(backtest_output["daily_file"]).suffix == ".parquet"
    assert Path(backtest_output["summary_file"]).suffix == ".parquet"
    assert set(backtest_output) == {"daily_file", "summary_file", "metadata_file", "days"}
    assert Path(backtest_output["metadata_file"]).is_file()
    assert {path.name for path in Path(backtest_output["metadata_file"]).parent.iterdir()} == {
        "daily.parquet",
        "summary.parquet",
        "metadata.json",
    }
    backtest_metadata = json.loads(Path(backtest_output["metadata_file"]).read_text())
    assert backtest_metadata["schema_version"] == 2
    assert backtest_metadata["dimensions"]["top_ns"] == [1, 2, 3, 5, 10, 15, 20, 30]
    assert backtest_metadata["artifacts"] == {"daily": "daily.parquet", "summary": "summary.parquet"}


def test_prediction_rejects_training_overlap(tmp_path):
    etl_task_id = _etl_fixture(tmp_path)
    training_dir = tmp_path / "training" / "training#fixture"
    training_dir.mkdir(parents=True)
    (training_dir / "model.txt").write_text("fixture", encoding="utf-8")
    (training_dir / "metadata.json").write_text(
        json.dumps(
            {
                "protocol": {"train_end_exclusive": "20230101"},
                "artifacts": {"model": "model.txt"},
                "source": {"etl_task_id": etl_task_id},
            },
        ),
        encoding="utf-8",
    )
    task = LgbmPredictionTask(
        {"training_task_id": "training#fixture", "pred_start": "20221231"},
        workspace_path=tmp_path,
    )

    with pytest.raises(ValueError, match="pred_start 不能早于 train_end"):
        task.execute()
