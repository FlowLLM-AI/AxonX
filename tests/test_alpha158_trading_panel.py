"""Contract tests for Alpha158 trading-calendar alignment."""

import polars as pl
import pytest
from axonx_alpha158.internal.etl_pipeline import align_calendar, load_index_weights


@pytest.mark.parametrize(
    ("quote_dates", "open_dates", "message"),
    [
        (["20260105"], ["20260106"], "行情范围内没有开市日"),
        (["20260105", "20260106"], ["20260105", "20260107"], "daily 包含非开市日期"),
    ],
)
def test_rejects_quotes_outside_open_market_dates(quote_dates, open_dates, message):
    """Quotes must fall on an open date inside their own date range."""
    frame = pl.DataFrame({"trade_date": quote_dates})
    calendar = pl.DataFrame({"trade_date": open_dates})

    with pytest.raises(ValueError, match=message):
        align_calendar(frame, calendar)


def test_rejects_duplicate_index_weight_snapshots(tmp_path):
    """One index constituent can have only one weight in a snapshot."""
    path = tmp_path / "index_weight.parquet"
    pl.DataFrame(
        {
            "index_code": ["000300.SH", "000300.SH"],
            "con_code": ["000001.SZ", "000001.SZ"],
            "trade_date": ["20260105", "20260105"],
            "weight": [50.0, 50.0],
        },
    ).write_parquet(path)

    with pytest.raises(ValueError, match="重复的 trade_date, con_code"):
        load_index_weights([path])
