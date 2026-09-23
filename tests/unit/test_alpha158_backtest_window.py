"""Prediction cutoffs for a backtest with unsettled top picks."""

import json
import subprocess
import sys

import polars as pl
import pytest

from axonx_alpha158 import backtest_window
from axonx_alpha158.backtest_window import settled_end


def predictions(path, unsafe_date=None):
    dates = ["20260105", "20260106", "20260107", "20260108", "20260109"]
    pl.DataFrame(
        {
            "trade_date": [date for date in dates for _ in range(2)],
            "ts_code": ["A", "B"] * len(dates),
            "pred": [2.0, 1.0] * len(dates),
            "is_buyable": [True] * (2 * len(dates)),
            "entry_is_buyable": [True] * (2 * len(dates)),
            "exit_is_sellable": [
                date != unsafe_date or code == "B"
                for date in dates
                for code in ("A", "B")
            ],
            "label_valid": [
                date != unsafe_date or code == "B"
                for date in dates
                for code in ("A", "B")
            ],
        }
    ).write_parquet(path)


def test_backtest_window_trims_only_unsettled_tail(tmp_path):
    path = tmp_path / "predictions.parquet"
    predictions(path, unsafe_date="20260107")
    assert settled_end(path) == "20260106"

    response = {
        "success": True,
        "answer": {"state": "succeeded", "result": {"predictions_file": str(path)}},
    }
    command = subprocess.run(
        [sys.executable, backtest_window.__file__],
        input=json.dumps(response),
        text=True,
        capture_output=True,
        check=True,
    )
    assert command.stdout.strip() == "20260106"

    predictions(path)
    assert settled_end(path) is None


def test_backtest_window_rejects_historical_missing_exit(tmp_path):
    path = tmp_path / "predictions.parquet"
    predictions(path, unsafe_date="20260105")
    with pytest.raises(ValueError, match="20260105"):
        settled_end(path)
