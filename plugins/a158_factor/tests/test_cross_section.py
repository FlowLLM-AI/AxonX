"""Verify information timing and amount grouping on a calendar-aligned panel."""

from datetime import date, timedelta

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from axonx_alpha158_factor.internal.cross_section import (
    CONTEXT_FEATURES,
    FEATURE_GROUPS,
    calculate_context,
    selected_features,
)
from axonx_alpha158.internal.etl_pipeline import FEATURES


def test_original_feature_contract_is_preserved():
    assert len(FEATURES) == 158


def panel(days=45):
    rows = []
    for symbol in range(12):
        for day in range(days):
            rows.append(
                {
                    "trade_date": (date(2020, 1, 1) + timedelta(days=day)).strftime("%Y%m%d"),
                    "ts_code": f"S{symbol:02d}",
                    "_close": 10 * (1 + (symbol - 5) * 0.001) ** day,
                    "amount": float((symbol + 1) * 100),
                    "vol": 100.0,
                    "_has_market_data": True,
                    "is_limit_up": symbol == 11,
                    "is_limit_down": symbol == 0,
                }
            )
    return pl.DataFrame(rows)


def test_future_changes_and_extra_future_rows_do_not_change_history():
    source = panel()
    cutoff = "20200204"
    baseline, daily = calculate_context(source)
    altered = source.with_columns(
        pl.when(pl.col("trade_date") > cutoff).then(pl.col("_close") * 2).otherwise(pl.col("_close")).alias("_close"),
        pl.when(pl.col("trade_date") > cutoff).then(pl.col("amount") * 100).otherwise(pl.col("amount")).alias("amount"),
    )
    changed, changed_daily = calculate_context(altered)
    prefix, prefix_daily = calculate_context(source.filter(pl.col("trade_date") <= cutoff))
    expected = baseline.filter(pl.col("trade_date") <= cutoff).sort("trade_date", "ts_code")
    assert_frame_equal(expected, changed.filter(pl.col("trade_date") <= cutoff).sort("trade_date", "ts_code"))
    assert_frame_equal(expected, prefix.sort("trade_date", "ts_code"))
    assert_frame_equal(
        daily.filter(pl.col("trade_date") <= cutoff), changed_daily.filter(pl.col("trade_date") <= cutoff)
    )
    assert_frame_equal(daily.filter(pl.col("trade_date") <= cutoff), prefix_daily)


def test_current_amount_jump_does_not_reassign_historical_amount_rank():
    source = panel()
    baseline, _ = calculate_context(source)
    changed, _ = calculate_context(
        source.with_columns(
            pl.when((pl.col("trade_date") == "20200204") & (pl.col("ts_code") == "S00"))
            .then(1e9)
            .otherwise(pl.col("amount"))
            .alias("amount"),
        )
    )
    columns = ["trade_date", "ts_code", "f_context_amount_rank20", "f_context_group_relative_return"]
    assert_frame_equal(
        baseline.filter(pl.col("trade_date") == "20200204").select(columns).sort("ts_code"),
        changed.filter(pl.col("trade_date") == "20200204").select(columns).sort("ts_code"),
    )
    assert changed.filter((pl.col("trade_date") == "20200204") & (pl.col("ts_code") == "S00"))[
        "f_context_stock_amount_ratio"
    ].item() == pytest.approx(1e7)


def test_limit_stocks_remain_in_pool_and_future_labels_are_ignored():
    source = panel()
    baseline, daily = calculate_context(source)
    changed, changed_daily = calculate_context(
        source.with_columns(
            pl.lit(False).alias("is_buyable"),
            pl.lit(None).alias("label_return"),
            pl.lit(False).alias("label_valid"),
        )
    )
    assert_frame_equal(baseline, changed)
    assert_frame_equal(daily, changed_daily)
    assert daily.filter(pl.col("trade_date") == "20200204")["market_count"].item() == 12
    assert daily.filter(pl.col("trade_date") == "20200204")["limit_up_ratio"].item() == pytest.approx(1 / 12)


def test_suspension_is_zero_amount_history_and_missing_adjacent_return():
    source = (
        panel()
        .with_columns(
            pl.when((pl.col("ts_code") == "S00") & (pl.col("trade_date") == "20200203"))
            .then(False)
            .otherwise(pl.col("_has_market_data"))
            .alias("_has_market_data"),
        )
        .with_columns(
            pl.when(pl.col("_has_market_data")).then(pl.col("_close")).otherwise(None).alias("_close"),
            pl.when(pl.col("_has_market_data")).then(pl.col("amount")).otherwise(None).alias("amount"),
        )
    )
    features, _ = calculate_context(source)
    assert (
        features.filter((pl.col("ts_code") == "S00") & (pl.col("trade_date") == "20200204"))[
            "f_context_relative_return"
        ].item()
        is None
    )
    row = features.filter((pl.col("ts_code") == "S00") & (pl.col("trade_date") == "20200205")).row(0, named=True)
    assert row["f_context_stock_amount_ratio"] == pytest.approx(100 / 95)


def test_ties_short_history_and_feature_group_validation():
    features, daily = calculate_context(panel(12).with_columns(pl.lit(100.0).alias("amount")))
    assert len(CONTEXT_FEATURES) == len(set(CONTEXT_FEATURES))
    assert features.filter(pl.col("trade_date") == "20200105")["f_context_amount_rank20"].null_count() == 12
    assert features.filter(pl.col("trade_date") == "20200112")["f_context_amount_rank20"].n_unique() == 1
    assert daily["amount_spread"].null_count() == 12
    assert not selected_features("none")
    assert selected_features("relative,market") == (*FEATURE_GROUPS["market"], *FEATURE_GROUPS["relative"])
    with pytest.raises(ValueError):
        selected_features("market,unknown")


def test_no_infinite_values_and_market_context_is_daily_constant():
    features, _ = calculate_context(panel())
    assert not features.select(pl.any_horizontal(pl.col(*CONTEXT_FEATURES).is_infinite())).to_series().any()
    assert (
        features.group_by("trade_date")
        .agg(pl.col("f_context_market_return").n_unique())["f_context_market_return"]
        .max()
        == 1
    )
