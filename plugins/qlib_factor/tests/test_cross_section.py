"""Verify global moment definitions, causal timing and baseline feature selection."""

from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest
from polars.testing import assert_frame_equal

from axonx_qlib_a158.internal.etl_pipeline import FEATURES
from axonx_qlib_factor.internal.cross_section import (
    CONTEXT_FEATURES,
    FEATURE_GROUPS,
    GLOBAL_FEATURES,
    WINDOWS,
    calculate_context,
    selected_features,
)


def panel(days=20):
    return pl.DataFrame(
        [
            {
                "trade_date": (date(2020, 1, 1) + timedelta(days=day)).strftime("%Y%m%d"),
                "ts_code": f"S{symbol:02d}",
                "_close": 10 * (1 + (symbol - 5) * 0.01) ** day,
                "amount": 100.0,
                "vol": 100.0,
                "_has_market_data": True,
            }
            for symbol in range(12)
            for day in range(days)
        ]
    )


def test_moments_match_independent_winsorized_reference_at_every_horizon():
    features, daily = calculate_context(panel())
    for window in WINDOWS:
        returns = np.array([(1 + (symbol - 5) * 0.01) ** window - 1 for symbol in range(12)])
        clipped = np.clip(returns, *np.quantile(returns, [0.02, 0.98]))
        row = daily.filter(pl.col("trade_date") == "20200120").row(0, named=True)
        assert row[f"market_count{window}"] == 12
        assert row[f"f_context_market_mean{window}"] == pytest.approx(clipped.mean())
        assert row[f"f_context_market_variance{window}"] == pytest.approx(clipped.var(ddof=1))
    assert len(GLOBAL_FEATURES) == 8
    assert len(CONTEXT_FEATURES) == 13
    assert (
        features.group_by("trade_date")
        .agg(pl.col(*GLOBAL_FEATURES).n_unique())
        .select(pl.col(*GLOBAL_FEATURES).max())
        .row(0)
        == (1,) * 8
    )


def test_future_changes_and_future_rows_do_not_change_history():
    source = panel()
    cutoff = "20200115"
    baseline, daily = calculate_context(source)
    changed, changed_daily = calculate_context(
        source.with_columns(
            pl.when(pl.col("trade_date") > cutoff)
            .then(pl.col("_close") * 2)
            .otherwise(pl.col("_close"))
            .alias("_close")
        )
    )
    prefix, prefix_daily = calculate_context(source.filter(pl.col("trade_date") <= cutoff))
    expected = baseline.filter(pl.col("trade_date") <= cutoff).sort("trade_date", "ts_code")
    assert_frame_equal(expected, changed.filter(pl.col("trade_date") <= cutoff).sort("trade_date", "ts_code"))
    assert_frame_equal(expected, prefix.sort("trade_date", "ts_code"))
    assert_frame_equal(
        daily.filter(pl.col("trade_date") <= cutoff), changed_daily.filter(pl.col("trade_date") <= cutoff)
    )
    assert_frame_equal(daily.filter(pl.col("trade_date") <= cutoff), prefix_daily)


def test_short_history_missing_quotes_and_nonfinite_prices():
    source = panel().with_columns(
        pl.when((pl.col("ts_code") == "S00") & (pl.col("trade_date") == "20200117"))
        .then(None)
        .otherwise(pl.col("_close"))
        .alias("_close"),
        pl.when((pl.col("ts_code") == "S01") & (pl.col("trade_date") == "20200120"))
        .then(0)
        .otherwise(pl.col("vol"))
        .alias("vol"),
    )
    features, daily = calculate_context(source)
    row = daily.filter(pl.col("trade_date") == "20200120").row(0, named=True)
    assert row["market_count3"] == 10
    assert row["market_count1"] == 11
    for window in WINDOWS:
        assert (
            features.filter(pl.col("trade_date") <= f"202001{window:02d}")[f"f_context_market_mean{window}"]
            .is_null()
            .all()
        )
    assert not features.select(pl.any_horizontal(pl.col(*CONTEXT_FEATURES).is_infinite())).to_series().any()


def test_empty_singleton_flat_pool_and_labels_ignored():
    source = panel().with_columns(pl.lit(10.0).alias("_close"))
    features, daily = calculate_context(source)
    changed, changed_daily = calculate_context(
        source.with_columns(pl.lit(False).alias("is_buyable"), pl.lit(1e9).alias("label_return"))
    )
    assert_frame_equal(features, changed)
    assert_frame_equal(daily, changed_daily)
    assert daily.tail(1)["f_context_market_variance10"].item() == 0
    _, singleton = calculate_context(source.filter(pl.col("ts_code") == "S00"))
    assert singleton["f_context_market_variance1"].is_null().all()
    _, empty = calculate_context(source.with_columns(pl.lit(0.0).alias("vol")))
    assert empty["f_context_market_mean1"].is_null().all()


def test_invalid_groups_and_baseline_selection():
    from axonx_qlib_factor.train import LgbmTrainInputParams, LgbmTrainTask

    assert len(FEATURES) == 158
    assert selected_features("variance,mean") == (*FEATURE_GROUPS["mean"], *FEATURE_GROUPS["variance"])
    assert not selected_features("none")
    for group in ("unknown", "none,mean", ""):
        with pytest.raises(ValueError):
            LgbmTrainInputParams(context_groups=group)
    task = object.__new__(LgbmTrainTask)
    task.input_params = LgbmTrainInputParams()
    unsupported = ("f_context_unknown",)
    with pytest.raises(ValueError, match="unsupported context features"):
        task.select_features((*FEATURES, *CONTEXT_FEATURES, *unsupported))
    assert task.select_features((*FEATURES, *CONTEXT_FEATURES)) == FEATURES
    task.input_params = LgbmTrainInputParams(context_groups="mean")
    assert task.select_features((*FEATURES, *CONTEXT_FEATURES)) == (*FEATURES, *FEATURE_GROUPS["mean"])


def test_horizon_ablation_selects_only_requested_columns_and_validates_inputs():
    from axonx_qlib_factor.train import LgbmTrainInputParams, LgbmTrainTask

    task = object.__new__(LgbmTrainTask)
    task.input_params = LgbmTrainInputParams(context_groups="mean,variance", context_windows=[10, 3, 10])
    assert task.input_params.context_windows == [3, 10]
    assert task.select_features((*FEATURES, *CONTEXT_FEATURES)) == (
        *FEATURES,
        "f_context_market_mean3",
        "f_context_market_mean10",
        "f_context_market_variance3",
        "f_context_market_variance10",
    )
    for windows in ([], [2], [0, 1]):
        with pytest.raises(ValueError):
            LgbmTrainInputParams(context_windows=windows)
    with pytest.raises(ValueError, match="missing requested"):
        task.select_features(FEATURES)


def dynamic_panel(days=100):
    rows = []
    for symbol in range(12):
        price = 10.0
        for day in range(days):
            if day:
                market = 0.015 * np.sin(day / 7) + 0.005 * np.cos(day / 3)
                price *= 1 + (0.3 + symbol * 0.15) * market + 0.005 * np.sin(day / (symbol + 2))
            rows.append(
                {
                    "trade_date": (date(2020, 1, 1) + timedelta(days=day)).strftime("%Y%m%d"),
                    "ts_code": f"S{symbol:02d}",
                    "_close": price,
                    "amount": 100.0,
                    "vol": 100.0,
                    "_has_market_data": True,
                }
            )
    return pl.DataFrame(rows)


def test_stock_momentum_and_risk_match_independent_prior_beta_reference():
    source = dynamic_panel()
    features, _ = calculate_context(source)
    closes = np.array([source.filter(pl.col("ts_code") == f"S{s:02d}")["_close"].to_numpy() for s in range(12)])
    returns = closes[:, 1:] / closes[:, :-1] - 1
    clipped = np.clip(returns, *np.quantile(returns, [0.02, 0.98], axis=0))
    market = clipped.mean(axis=0)

    def beta(symbol, day):
        stock_prior = clipped[symbol, : day - 1][-60:]
        market_prior = market[: day - 1][-60:]
        return np.clip(np.cov(stock_prior, market_prior, ddof=1)[0, 1] / np.var(market_prior, ddof=1), -3, 3)

    for symbol in (0, 5, 11):
        actual = features.filter(pl.col("ts_code") == f"S{symbol:02d}").tail(1).row(0, named=True)
        for window in (5, 10, 20):
            expected = closes[symbol, -1] / closes[symbol, -1 - window] - 1
            expected -= beta(symbol, 99) * (np.prod(1 + market[-window:]) - 1)
            assert actual[f"f_context_neutral_momentum{window}"] == pytest.approx(expected, abs=1e-10)
        residuals = [clipped[symbol, day - 1] - beta(symbol, day) * market[day - 1] for day in range(80, 100)]
        assert actual["f_context_residual_vol20"] == pytest.approx(np.std(residuals, ddof=1), abs=1e-10)
        assert actual["f_context_downside_risk20"] == pytest.approx(
            np.sqrt(np.mean(np.minimum(clipped[symbol, -20:], 0) ** 2)), abs=1e-10
        )


def test_stock_features_remain_causal_with_full_beta_history():
    source = dynamic_panel()
    cutoff = "20200315"
    baseline, _ = calculate_context(source)
    changed, _ = calculate_context(
        source.with_columns(
            pl.when(pl.col("trade_date") > cutoff)
            .then(pl.col("_close") * 2)
            .otherwise(pl.col("_close"))
            .alias("_close")
        )
    )
    prefix, _ = calculate_context(source.filter(pl.col("trade_date") <= cutoff))
    expected = baseline.filter(pl.col("trade_date") <= cutoff).sort("trade_date", "ts_code")
    assert_frame_equal(expected, changed.filter(pl.col("trade_date") <= cutoff).sort("trade_date", "ts_code"))
    assert_frame_equal(expected, prefix.sort("trade_date", "ts_code"))
    assert selected_features("neutral,risk", (10,)) == (*FEATURE_GROUPS["neutral"], *FEATURE_GROUPS["risk"])


def test_nonfinite_endpoints_are_excluded_and_undefined_beta_stays_null():
    source = panel().with_columns(
        pl.when((pl.col("ts_code") == "S00") & (pl.col("trade_date") == "20200117"))
        .then(float("inf"))
        .otherwise(pl.col("_close"))
        .alias("_close")
    )
    _, daily = calculate_context(source)
    assert daily.filter(pl.col("trade_date") == "20200120")["market_count3"].item() == 11
    features, _ = calculate_context(panel(100).with_columns(pl.lit(10.0).alias("_close")))
    assert features["f_context_residual_vol20"].is_null().all()
    assert features["f_context_neutral_momentum10"].is_null().all()
    assert features.tail(1)["f_context_downside_risk20"].item() == 0


@pytest.mark.parametrize("invalid", ["missing", "zero_volume", "nonfinite"])
def test_stock_features_are_null_on_invalid_current_quotes(invalid):
    source = dynamic_panel()
    last = source["trade_date"].max()
    features, _ = calculate_context(source)
    valid = features.filter((pl.col("ts_code") == "S00") & (pl.col("trade_date") == last))
    assert valid["f_context_residual_vol20"].item() is not None
    bad = (pl.col("ts_code") == "S00") & (pl.col("trade_date") == last)
    column, value = {
        "missing": ("_has_market_data", False),
        "zero_volume": ("vol", 0.0),
        "nonfinite": ("_close", float("inf")),
    }[invalid]
    changed, _ = calculate_context(
        source.with_columns(pl.when(bad).then(pl.lit(value)).otherwise(pl.col(column)).alias(column))
    )
    row = changed.filter(bad).row(0, named=True)
    assert all(row[name] is None for group in ("neutral", "risk") for name in FEATURE_GROUPS[group])
