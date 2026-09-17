"""Index membership filtering for backtest candidates."""

import json

import polars as pl
import pytest

from axonx.task.core import BacktestTask


def _prediction_source(tmp_path):
    task_id = "predict#fixture#index-filter"
    source = tmp_path / "predict" / task_id
    source.mkdir(parents=True)
    rows = []
    for trade_date in ("20260105", "20260106"):
        for code, pred, hs300, zz500 in (
            ("A", 0.9, 0.0, 0.5),
            ("B", 0.8, 0.6, 0.0),
            ("C", 0.7, 0.4, 0.5),
        ):
            rows.append(
                {
                    "trade_date": trade_date,
                    "ts_code": code,
                    "name": code,
                    "pred": pred,
                    "actual_return": pred / 100,
                    "label_valid": True,
                    "is_buyable": True,
                    "index_weight_hs300": hs300,
                    "index_weight_zz500": zz500,
                }
            )
    pl.DataFrame(rows).write_parquet(source / "predictions.parquet")
    (source / "metadata.json").write_text(
        json.dumps(
            {
                "output_params": {
                    "protocol": {"actual_return_unit": "decimal"},
                    "artifacts": {"predictions": {"path": "predictions.parquet"}},
                },
            }
        ),
        encoding="utf-8",
    )
    return task_id


@pytest.mark.parametrize(
    ("index_filter", "count", "top1", "normalized"),
    [
        ("", 3, "A", []),
        ("HS300", 2, "B", ["hs300"]),
        ("hS300，ZZ500", 3, "A", ["hs300", "zz500"]),
    ],
)
def test_index_filter_applies_before_ranking(
    tmp_path, index_filter, count, top1, normalized
):
    source_id = _prediction_source(tmp_path)
    task = BacktestTask(
        {"source_tasks": [source_id], "index_filter": index_filter},
        workspace_path=tmp_path,
    )
    result = task.execute()
    daily = pl.read_parquet(result["daily_file"])
    assert daily["candidate_count"].to_list() == [count, count]
    assert daily["top30_holdings"][0][0]["ts_code"] == top1
    assert result["dimensions"]["index_filter"] == normalized


def test_unknown_index_reports_available_columns(tmp_path):
    source_id = _prediction_source(tmp_path)
    task = BacktestTask(
        {"source_tasks": [source_id], "index_filter": "ZZ1000"},
        workspace_path=tmp_path,
    )
    with pytest.raises(ValueError, match="zz1000.*hs300, zz500"):
        task.execute()
