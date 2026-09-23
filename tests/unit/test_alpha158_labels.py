"""Check the signal date and executable return window."""

import polars as pl

from axonx_alpha158.internal.etl_pipeline import LABEL_OUTPUTS, calculate_labels


def test_label_uses_next_two_market_opens_without_skipping_suspensions():
    dates = ["20260105", "20260106", "20260107", "20260108"]
    frame = pl.DataFrame(
        {
            "ts_code": ["A"] * 4 + ["B"] * 4,
            "trade_date": dates * 2,
            "_open": [10.0, 11.0, 12.0, 13.0, 20.0, None, 22.0, 23.0],
            "open": [10.0, 11.0, 12.0, 13.0, 20.0, None, 22.0, 23.0],
            "up_limit": [15.0] * 4 + [25.0] * 4,
            "down_limit": [5.0] * 4 + [15.0] * 4,
            "_has_market_data": [True] * 4 + [True, False, True, True],
            "_has_valid_limits": [True] * 8,
            "is_st": [False] * 8,
            "is_delisting": [False] * 8,
        }
    )
    output = calculate_labels(frame, 0.025)
    assert LABEL_OUTPUTS == ("label_1d", "label_1d_csz", "label_1d_rank", "label_1d_is_valid")
    first = output.filter((pl.col("ts_code") == "A") & (pl.col("trade_date") == dates[0])).row(0, named=True)
    assert abs(first["label_1d"] - (12 / 11 - 1)) < 1e-12
    assert (first["entry_date"], first["exit_date"]) == (dates[1], dates[2])
    assert first["entry_is_buyable"] and first["exit_is_sellable"]
    suspended = output.filter((pl.col("ts_code") == "B") & (pl.col("trade_date") == dates[0])).row(0, named=True)
    assert not suspended["label_1d_is_valid"]
    assert not suspended["entry_is_buyable"]
    assert output.filter(pl.col("trade_date") == dates[-1])["label_1d_is_valid"].to_list() == [False, False]
