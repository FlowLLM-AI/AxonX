"""Causal market moments, stock momentum/risk and ordered feature selection."""

from collections.abc import Sequence
from typing import Literal

import polars as pl

ContextGroup = Literal["mean", "variance", "neutral", "risk"]
ContextWindow = Literal[1, 3, 5, 10]
PREFIX = "f_context_"
WINDOWS = (1, 3, 5, 10)
NEUTRAL_WINDOWS = (5, 10, 20)
BETA_WINDOW = 60
RISK_WINDOW = 20
WINSORIZE_TAIL = 0.02
FEATURE_GROUPS = {
    **{
        statistic: tuple(f"{PREFIX}market_{statistic}{window}" for window in WINDOWS)
        for statistic in ("mean", "variance")
    },
    "neutral": tuple(f"{PREFIX}neutral_momentum{window}" for window in NEUTRAL_WINDOWS),
    "risk": (f"{PREFIX}residual_vol20", f"{PREFIX}downside_risk20"),
}
GLOBAL_FEATURES = (*FEATURE_GROUPS["mean"], *FEATURE_GROUPS["variance"])
STOCK_FEATURES = (*FEATURE_GROUPS["neutral"], *FEATURE_GROUPS["risk"])
CONTEXT_FEATURES = (*GLOBAL_FEATURES, *STOCK_FEATURES)


def selected_features(groups: Sequence[ContextGroup], windows: Sequence[int] = WINDOWS) -> tuple[str, ...]:
    """Expand selected groups in canonical column order; an empty selection uses the baseline."""
    if unknown := set(groups) - FEATURE_GROUPS.keys():
        raise ValueError(f"Unknown context groups: {sorted(unknown)}")
    if not windows or set(windows) - set(WINDOWS):
        raise ValueError(f"Context windows must be selected from {WINDOWS}")
    return tuple(
        feature
        for group, features in FEATURE_GROUPS.items()
        if group in groups
        for index, feature in enumerate(features)
        if group not in ("mean", "variance") or WINDOWS[index] in windows
    )


def _winsorize(value: pl.Expr) -> pl.Expr:
    return value.clip(
        value.quantile(WINSORIZE_TAIL, interpolation="linear").over("trade_date"),
        value.quantile(1 - WINSORIZE_TAIL, interpolation="linear").over("trade_date"),
    )


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
    panel = panel.with_columns(_winsorize(pl.col("_return1")).alias("_stock_ret"))
    daily = panel.select("trade_date").unique().sort("trade_date")
    for window in WINDOWS:
        column = f"_return{window}"
        value = pl.col("_stock_ret") if window == 1 else pl.col(column)
        pool = panel.select("trade_date", value.alias(column)).filter(pl.col(column).is_not_null())
        if window != 1:
            pool = pool.with_columns(_winsorize(pl.col(column)))
        moments = pool.group_by("trade_date").agg(
            pl.len().alias(f"market_count{window}"),
            pl.col(column).mean().alias(f"{PREFIX}market_mean{window}"),
            pl.col(column).var(ddof=1).alias(f"{PREFIX}market_variance{window}"),
        )
        daily = daily.join(moments, on="trade_date", how="left", maintain_order="left")
    features = panel.select(keys).join(daily.select("trade_date", *GLOBAL_FEATURES), on="trade_date", how="left")
    features = features.join(_stock_features(panel, daily), on=keys, how="left", maintain_order="left")
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
        "outliers": "per-date/per-horizon 2%/98% linear-quantile winsorization",
        "moments": "equal-weight mean and sample variance (ddof=1); empty/singleton variance remains null",
        "common_context_diagnostic": "global mean/variance have no cross-sectional IC; evaluate model ablations",
        "stock_beta": "paired winsorized stock/market returns; prior60 calendar days, min30; beta clipped [-3,3]",
        "neutral_momentum": "stock cumulative 5/10/20-day return minus prior beta times compounded market return",
        "residual_vol20": "sample std of daily stock-minus-prior-beta-market residuals; min16/20 valid observations",
        "downside_risk20": "sqrt(mean(min(winsorized stock return,0)^2)); min16/20 valid observations",
    }


def _stock_features(panel: pl.DataFrame, daily: pl.DataFrame) -> pl.DataFrame:
    """Estimate beta on paired past returns; publish causal momentum and risk.

    Clip stock daily returns at contemporaneous 2%/98% linear quantiles.
    Beta uses 60 calendar trading days through T-1, at least 30 paired quotes,
    covariance/market variance, clipped to [-3,3]. Market returns are the daily
    winsorized equal-weight mean. Risk windows need 16 valid returns out of 20;
    missing quotes stay null. Undefined market variance leaves beta undefined.
    """
    market = daily.select(
        "trade_date",
        pl.col("f_context_market_mean1").alias("_market_ret"),
        *[
            (pl.col("f_context_market_mean1").log1p().rolling_sum(window, min_samples=window).exp() - 1).alias(
                f"_market_cum{window}"
            )
            for window in NEUTRAL_WINDOWS
        ],
    )
    panel = panel.join(market, on="trade_date", how="left", maintain_order="left").with_columns(
        pl.when(pl.col("_quoted") & pl.col("_quoted").shift(20).over("ts_code"))
        .then(pl.col("_close") / pl.col("_close").shift(20).over("ts_code") - 1)
        .alias("_return20"),
    )
    paired = pl.col("_stock_ret").is_finite() & pl.col("_market_ret").is_finite()
    stock = pl.when(paired).then(pl.col("_stock_ret"))
    market_return = pl.when(paired).then(pl.col("_market_ret"))
    panel = panel.with_columns(
        *[
            expression.rolling_mean(BETA_WINDOW, min_samples=30).shift(1).over("ts_code").alias(name)
            for name, expression in (
                ("_s_mean", stock),
                ("_m_mean", market_return),
                ("_sm_mean", stock * market_return),
                ("_mm_mean", market_return.pow(2)),
            )
        ]
    )
    variance = pl.col("_mm_mean") - pl.col("_m_mean").pow(2)
    covariance = pl.col("_sm_mean") - pl.col("_s_mean") * pl.col("_m_mean")
    panel = panel.with_columns(
        pl.when(variance > 1e-12).then((covariance / variance).clip(-3, 3)).alias("_beta")
    ).with_columns((pl.col("_stock_ret") - pl.col("_beta") * pl.col("_market_ret")).alias("_residual"))
    panel = panel.with_columns(
        *[
            (pl.col(f"_return{window}") - pl.col("_beta") * pl.col(f"_market_cum{window}")).alias(name)
            for window, name in zip(NEUTRAL_WINDOWS, FEATURE_GROUPS["neutral"], strict=True)
        ],
        pl.col("_residual")
        .rolling_std(RISK_WINDOW, min_samples=16, ddof=1)
        .over("ts_code")
        .alias(FEATURE_GROUPS["risk"][0]),
        pl.col("_stock_ret")
        .clip(upper_bound=0)
        .pow(2)
        .rolling_mean(RISK_WINDOW, min_samples=16)
        .sqrt()
        .over("ts_code")
        .alias(FEATURE_GROUPS["risk"][1]),
    )
    return panel.select(
        "trade_date",
        "ts_code",
        *[
            pl.when(pl.col("_quoted") & pl.col(name).is_finite()).then(pl.col(name)).alias(name)
            for name in STOCK_FEATURES
        ],
    )
