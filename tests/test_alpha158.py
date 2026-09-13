from pathlib import Path

import polars as pl
import pytest

from axonx.task.etl import Alpha158Task
from axonx.task.etl.alpha158 import FEATURES, LABELS


def _write_partition(root: Path, trade_date: str, name: str, rows: list[dict]) -> None:
    path = root / "tushare" / trade_date[:4] / trade_date / f"{name}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_parquet(path)


def test_alpha158_builds_strict_forward_labels_and_snapshot_weights(tmp_path):
    quotes = {
        "20260105": [("000001.SZ", 10.0), ("000002.SZ", 20.0)],
        "20260106": [("000001.SZ", 11.0)],
        "20260107": [("000001.SZ", 12.0), ("000002.SZ", 22.0)],
    }
    for trade_date, stocks in quotes.items():
        _write_partition(
            tmp_path,
            trade_date,
            "daily",
            [
                {
                    "ts_code": code,
                    "trade_date": trade_date,
                    "open": close - 0.2,
                    "high": close + 0.5,
                    "low": close - 0.5,
                    "close": close,
                    "vol": 1000.0,
                    "amount": close * 100.0,
                }
                for code, close in stocks
            ],
        )
        _write_partition(
            tmp_path,
            trade_date,
            "adj_factor",
            [
                {"ts_code": code, "trade_date": trade_date, "adj_factor": 1.0}
                for code, _ in stocks
            ],
        )

    _write_partition(
        tmp_path,
        "20260105",
        "index_weight",
        [
            {
                "index_code": "000300.SH",
                "con_code": "000001.SZ",
                "trade_date": "20260105",
                "weight": 60.0,
            },
            {
                "index_code": "000300.SH",
                "con_code": "000002.SZ",
                "trade_date": "20260105",
                "weight": 40.0,
            },
        ],
    )
    _write_partition(
        tmp_path,
        "20260107",
        "index_weight",
        [
            {
                "index_code": "000300.SH",
                "con_code": "000002.SZ",
                "trade_date": "20260107",
                "weight": 100.0,
            }
        ],
    )

    output = Alpha158Task({}, workspace_path=tmp_path).execute()
    result = pl.read_parquet(output["output_file"])

    assert output["feature_count"] == 158
    assert result.columns == [
        "trade_date",
        "ts_code",
        *FEATURES,
        *LABELS,
        "index_weight_hs300",
    ]
    assert result.filter(pl.col("ts_code") == "000001.SZ")[
        "label_1d"
    ].to_list() == pytest.approx(
        [0.1, 1 / 11, None],
        nan_ok=True,
    )
    assert result.filter(pl.col("ts_code") == "000001.SZ")[
        "label_2d"
    ].to_list() == pytest.approx([0.2, None, None], nan_ok=True)
    assert result.filter(pl.col("ts_code") == "000002.SZ")["label_1d"].to_list() == [
        None,
        None,
    ]
    assert result.filter(pl.col("ts_code") == "000002.SZ")[
        "label_2d"
    ].to_list() == pytest.approx([0.1, None], nan_ok=True)
    assert result["index_weight_hs300"].to_list() == pytest.approx(
        [0.6, 0.4, 0.6, 0.0, 1.0]
    )
    # The missing 20260106 quote remains a calendar row inside B's rolling window.
    b_last = result.filter(
        (pl.col("ts_code") == "000002.SZ") & (pl.col("trade_date") == "20260107")
    )
    assert b_last["f_alpha158_CNTP5"].item() == pytest.approx(0.0)
