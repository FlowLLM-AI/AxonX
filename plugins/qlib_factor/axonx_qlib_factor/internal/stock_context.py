"""Stock-level market-neutral momentum and return risk using prior market beta."""

import polars as pl

FEATURE_GROUPS = {
    "neutral": tuple(f"f_context_neutral_momentum{window}" for window in (5, 10, 20)),
    "risk": ("f_context_residual_vol20", "f_context_downside_risk20"),
}
STOCK_FEATURES = tuple(feature for features in FEATURE_GROUPS.values() for feature in features)


def calculate_stock_context(panel: pl.DataFrame, daily: pl.DataFrame) -> pl.DataFrame:
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
            for window in (5, 10, 20)
        ],
    )
    panel = panel.join(market, on="trade_date", how="left", maintain_order="left").with_columns(
        pl.col("_return1")
        .clip(
            pl.col("_return1").quantile(0.02, interpolation="linear").over("trade_date"),
            pl.col("_return1").quantile(0.98, interpolation="linear").over("trade_date"),
        )
        .alias("_stock_ret"),
        pl.when(pl.col("_quoted") & pl.col("_quoted").shift(20).over("ts_code"))
        .then(pl.col("_close") / pl.col("_close").shift(20).over("ts_code") - 1)
        .alias("_return20"),
    )
    paired = pl.col("_stock_ret").is_finite() & pl.col("_market_ret").is_finite()
    stock = pl.when(paired).then(pl.col("_stock_ret"))
    market_return = pl.when(paired).then(pl.col("_market_ret"))
    panel = panel.with_columns(
        *[
            expression.rolling_mean(60, min_samples=30).shift(1).over("ts_code").alias(name)
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
            for window, name in zip((5, 10, 20), FEATURE_GROUPS["neutral"], strict=True)
        ],
        pl.col("_residual").rolling_std(20, min_samples=16, ddof=1).over("ts_code").alias(FEATURE_GROUPS["risk"][0]),
        pl.col("_stock_ret")
        .clip(upper_bound=0)
        .pow(2)
        .rolling_mean(20, min_samples=16)
        .sqrt()
        .over("ts_code")
        .alias(FEATURE_GROUPS["risk"][1]),
    )
    return panel.select(
        "trade_date",
        "ts_code",
        *[pl.when(pl.col(name).is_finite()).then(pl.col(name)).alias(name) for name in STOCK_FEATURES],
    )
