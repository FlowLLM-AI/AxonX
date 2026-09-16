"""Contract tests for Alpha158 quote validation boundaries."""

import polars as pl
import pytest

from axonx.task.alpha158.internal.etl_pipeline import fill_missing_adj_factors, validate_market_data


def _quote(**changes: object) -> pl.DataFrame:
    row = {
        "ts_code": "000001.SZ",
        "trade_date": "20260105",
        "open": 10.0,
        "high": 10.0,
        "low": 10.0,
        "close": 10.0,
        "pre_close": 10.0,
        "vol": 100.0,
        "amount": 1000.0,
        "adj_factor": 1.0,
    }
    row.update(changes)
    return pl.DataFrame([row])


def test_rejects_duplicate_quote_keys():
    """Duplicate symbol/date pairs must be rejected before factor repair."""
    frame = _quote()

    with pytest.raises(ValueError, match="重复的 ts_code, trade_date"):
        fill_missing_adj_factors(pl.concat([frame, frame]))


@pytest.mark.parametrize(
    "changes",
    [
        {"trade_date": "2026-01-05"},
        {"open": 0.0},
        {"vol": -1.0},
        {"adj_factor": float("inf")},
    ],
)
def test_rejects_invalid_quote_values(changes):
    """Dates and numeric values must retain the existing input bounds."""
    with pytest.raises(ValueError, match="缺失、非有限或越界数据"):
        validate_market_data(_quote(**changes))
