"""Causal global market moments and stock-level market-neutral momentum/risk."""

from __future__ import annotations

import polars as pl

from .stock_context import FEATURE_GROUPS as STOCK_GROUPS, calculate_stock_context

PREFIX = "f_context_"
WINDOWS = (1, 3, 5, 10)
WINSORIZE_TAIL = 0.02
FEATURE_GROUPS = {
    statistic: tuple(f"{PREFIX}market_{statistic}{window}" for window in WINDOWS) for statistic in ("mean", "variance")
}
GLOBAL_FEATURES = tuple(feature for features in FEATURE_GROUPS.values() for feature in features)
FEATURE_GROUPS.update(STOCK_GROUPS)
CONTEXT_FEATURES = tuple(feature for features in FEATURE_GROUPS.values() for feature in features)


def selected_features(groups: str, windows: tuple[int, ...] = WINDOWS) -> tuple[str, ...]:
    """Select mean/variance groups, or 'none' for the Alpha158 control."""
    names = tuple(dict.fromkeys(value.strip() for value in groups.split(",") if value.strip()))
    if names == ("none",):
        return ()
    unknown = set(names) - FEATURE_GROUPS.keys()
    if not names or unknown:
        raise ValueError(f"Unknown context groups: {sorted(unknown)}; use {tuple(FEATURE_GROUPS)} or none")
    if not windows or set(windows) - set(WINDOWS):
        raise ValueError(f"Context windows must be selected from {WINDOWS}")
    selected = []
    for group, features in FEATURE_GROUPS.items():
        if group not in names:
            continue
        if group in ("mean", "variance"):
            selected.extend(feature for window, feature in zip(WINDOWS, features, strict=True) if window in windows)
        else:
            selected.extend(features)
    return tuple(selected)


def calculate_context(frame: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Repeat daily market moments and attach stock-level momentum/risk.

    Use adjusted T / T-h closes on the complete trading calendar. Require quotes
    and positive volume/amount at both endpoints; never forward-fill suspensions.
    Each horizon has its own finite-return pool, including price-limit stocks.
    Bounds use only that date's pool. Empty pools stay null; sample variance is
    null for fewer than two observations. No label or future tradability is used.
    """
    keys = ["trade_date", "ts_code"]
    panel = frame.select(*keys, "_close", "amount", "vol", "_has_market_data").sort("ts_code", "trade_date")
    panel = panel.with_columns(
        (
            pl.col("_has_market_data")
            & (pl.col("vol") > 0)
            & (pl.col("amount") > 0)
            & (pl.col("_close") > 0)
            & pl.col("_close").is_finite()
            & pl.col("amount").is_finite()
            & pl.col("vol").is_finite()
        )
        .fill_null(False)
        .alias("_quoted")
    )
    panel = panel.with_columns(
        *[
            pl.when(pl.col("_quoted") & pl.col("_quoted").shift(window).over("ts_code"))
            .then(pl.col("_close") / pl.col("_close").shift(window).over("ts_code") - 1)
            .alias(f"_return{window}")
            for window in WINDOWS
        ]
    ).with_columns(
        *[
            pl.when(pl.col(f"_return{window}").is_finite()).then(pl.col(f"_return{window}")).alias(f"_return{window}")
            for window in WINDOWS
        ]
    )
    daily = panel.select("trade_date").unique().sort("trade_date")
    for window in WINDOWS:
        column = f"_return{window}"
        pool = panel.filter(pl.col(column).is_not_null()).select("trade_date", column)
        pool = pool.with_columns(
            pl.col(column).clip(
                pl.col(column).quantile(WINSORIZE_TAIL, interpolation="linear").over("trade_date"),
                pl.col(column).quantile(1 - WINSORIZE_TAIL, interpolation="linear").over("trade_date"),
            )
        )
        moments = pool.group_by("trade_date").agg(
            pl.len().alias(f"market_count{window}"),
            pl.col(column).mean().alias(f"{PREFIX}market_mean{window}"),
            pl.col(column).var(ddof=1).alias(f"{PREFIX}market_variance{window}"),
        )
        daily = daily.join(moments, on="trade_date", how="left", maintain_order="left")
    features = panel.select(keys).join(daily.select("trade_date", *GLOBAL_FEATURES), on="trade_date", how="left")
    features = features.join(calculate_stock_context(panel, daily), on=keys, how="left", maintain_order="left")
    return features, daily


def context_protocol() -> dict:
    """Describe the feature definition and causal information set in ETL metadata."""
    return {
        "feature_groups": {name: list(columns) for name, columns in FEATURE_GROUPS.items()},
        "signal_time": "T close; no forward labels or future tradability used",
        "return": "adjusted close(T)/adjusted close(T-h)-1; h=1,3,5,10 trading-calendar days",
        "market_pool": (
            "positive adjusted close, volume and amount with quotes at both endpoints; includes limit stocks"
        ),
        "outliers": "per-date/per-horizon 2%/98% linear-quantile winsorization, matching Axon2 reference",
        "moments": "equal-weight mean and sample variance (ddof=1); empty/singleton variance remains null",
        "common_context_diagnostic": "global mean/variance have no cross-sectional IC; evaluate model ablations",
        "stock_beta": "paired winsorized stock/market returns; prior60 calendar days, min30; beta clipped [-3,3]",
        "neutral_momentum": "stock cumulative 5/10/20-day return minus prior beta times compounded market return",
        "residual_vol20": "sample std of daily stock-minus-prior-beta-market residuals; min16/20 valid observations",
        "downside_risk20": "sqrt(mean(min(winsorized stock return,0)^2)); min16/20 valid observations",
        "retired_groups": ["market", "liquidity", "relative", "interaction"],
    }
