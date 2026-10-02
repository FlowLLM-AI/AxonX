"""Causal daily market context and turnover-amount cross-sectional features."""

from __future__ import annotations

import polars as pl

PREFIX = "f_context_"
GROUPS = {
    "market": (
        "market_return",
        "market_median",
        "advance_ratio",
        "return_iqr",
        "limit_up_ratio",
        "limit_down_ratio",
        "market_trend5",
        "market_trend20",
        "market_shock",
        "market_amount_ratio",
        "amount_concentration",
    ),
    "liquidity": (
        "amount_rank20",
        "stock_amount_ratio",
        "low_amount_return",
        "high_amount_return",
        "amount_spread",
        "amount_spread5",
    ),
    "relative": (
        "relative_return",
        "group_relative_return",
        "return_rank",
        "relative_trend5",
        "relative_trend20",
    ),
    "interaction": (
        "shock_x_relative",
        "down_x_relative",
        "spread_x_amount_rank",
        "amount_x_stock_amount",
    ),
}
FEATURE_GROUPS = {group: tuple(PREFIX + name for name in names) for group, names in GROUPS.items()}
CONTEXT_FEATURES = tuple(feature for features in FEATURE_GROUPS.values() for feature in features)


def selected_features(groups: str) -> tuple[str, ...]:
    """Resolve an explicit set of groups, accepting 'none' for the baseline."""
    names = tuple(dict.fromkeys(value.strip() for value in groups.split(",") if value.strip()))
    if names == ("none",):
        return ()
    if not names or (unknown := set(names) - FEATURE_GROUPS.keys()):
        raise ValueError(f"Unknown context groups: {sorted(unknown) if names else groups}; use {tuple(GROUPS)} or none")
    # Stable order independent of user input, matching ETL metadata.
    return tuple(feature for group, features in FEATURE_GROUPS.items() if group in names for feature in features)


def calculate_context(frame: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Return row features and a daily diagnostic table without any forward labels.

    Input is the complete trading-calendar panel. Amount history ends at T-1;
    suspended days contribute zero amount. Returns use adjusted consecutive
    calendar closes, so missing adjacent quotes are not bridged. Market summaries
    include limit stocks and never consult future labels or buyability.
    """
    keys = ["trade_date", "ts_code"]
    panel = frame.select(
        *keys,
        "_close",
        "amount",
        "vol",
        "_has_market_data",
        "is_limit_up",
        "is_limit_down",
    ).sort("ts_code", "trade_date")
    panel = panel.with_columns(
        (pl.col("_close") / pl.col("_close").shift(1).over("ts_code") - 1).alias("_ret"),
        pl.when(pl.col("_has_market_data"))
        .then(pl.col("amount"))
        .otherwise(0.0)
        .rolling_mean(window_size=20, min_samples=10)
        .shift(1)
        .over("ts_code")
        .alias("_amount20"),
        *[
            (pl.col("_close") / pl.col("_close").shift(window).over("ts_code") - 1).alias(f"_trend{window}")
            for window in (5, 20)
        ],
    ).with_columns(
        (pl.col("_has_market_data") & (pl.col("vol") > 0) & (pl.col("amount") > 0) & pl.col("_ret").is_finite())
        .fill_null(False)
        .alias("_pool"),
    )
    historical_amount = pl.when(pl.col("_pool") & (pl.col("_amount20") > 0)).then(pl.col("_amount20"))
    pool_ret = pl.when(pl.col("_pool")).then(pl.col("_ret"))
    panel = panel.with_columns(
        (
            historical_amount.rank(method="average").over("trade_date") / historical_amount.count().over("trade_date")
        ).alias("amount_rank20"),
        (pool_ret.rank(method="average").over("trade_date") / pool_ret.count().over("trade_date")).alias("return_rank"),
        pl.when(pl.col("_pool") & (pl.col("_amount20") > 0))
        .then(pl.col("amount") / pl.col("_amount20"))
        .alias("stock_amount_ratio"),
    ).with_columns(
        (pl.col("amount_rank20") * 3).floor().clip(0, 2).cast(pl.Int8).alias("_amount_group"),
    )
    pool = panel.filter("_pool")
    pool = pool.with_columns(
        pl.col("amount").rank(method="average", descending=True).over("trade_date").alias("_amount_today_rank"),
    )
    daily = pool.group_by("trade_date").agg(
        pl.len().alias("market_count"),
        pl.col("_amount_group").is_not_null().sum().alias("amount_group_count"),
        pl.col("_ret").mean().alias("market_return"),
        pl.col("_ret").median().alias("market_median"),
        (pl.col("_ret") > 0).mean().alias("advance_ratio"),
        (
            pl.col("_ret").quantile(0.75, interpolation="linear")
            - pl.col("_ret").quantile(0.25, interpolation="linear")
        ).alias("return_iqr"),
        pl.col("is_limit_up").mean().alias("limit_up_ratio"),
        pl.col("is_limit_down").mean().alias("limit_down_ratio"),
        pl.col("amount").sum().alias("market_amount"),
        (
            pl.col("amount").filter(pl.col("_amount_today_rank") <= (pl.len() * 0.1).ceil()).sum()
            / pl.col("amount").sum()
        ).alias("amount_concentration"),
        pl.col("_ret").filter(pl.col("_amount_group") == 0).mean().alias("low_amount_return"),
        pl.col("_ret").filter(pl.col("_amount_group") == 2).mean().alias("high_amount_return"),
    )
    # Retain every calendar day even if the market pool is empty on one day.
    daily = panel.select("trade_date").unique().sort("trade_date").join(daily, on="trade_date", how="left")
    daily = daily.with_columns(
        (pl.col("high_amount_return") - pl.col("low_amount_return")).alias("amount_spread"),
        *[
            (pl.col("market_return").log1p().rolling_sum(window_size=window, min_samples=window).exp() - 1).alias(
                f"market_trend{window}"
            )
            for window in (5, 20)
        ],
        pl.col("market_return").rolling_std(window_size=20, min_samples=10).shift(1).alias("_market_vol20"),
        pl.col("market_return").rolling_mean(window_size=20, min_samples=10).shift(1).alias("_market_mean20"),
        pl.col("market_amount").rolling_mean(window_size=20, min_samples=10).shift(1).alias("_market_amount20"),
    ).with_columns(
        pl.when(pl.col("_market_vol20") > 1e-12)
        .then((pl.col("market_return") - pl.col("_market_mean20")) / pl.col("_market_vol20"))
        .alias("market_shock"),
        pl.when(pl.col("_market_amount20") > 0)
        .then(pl.col("market_amount") / pl.col("_market_amount20"))
        .alias("market_amount_ratio"),
        pl.col("amount_spread").rolling_mean(window_size=5, min_samples=5).alias("amount_spread5"),
    )
    group_returns = (
        pool.filter(pl.col("_amount_group").is_not_null())
        .group_by("trade_date", "_amount_group")
        .agg(
            pl.col("_ret").mean().alias("_group_return"),
        )
    )
    panel = (
        panel.join(daily, on="trade_date", how="left")
        .join(
            group_returns,
            on=["trade_date", "_amount_group"],
            how="left",
        )
        .with_columns(
            pl.when(pl.col("_pool")).then(pl.col("_ret") - pl.col("market_return")).alias("relative_return"),
            pl.when(pl.col("_pool")).then(pl.col("_ret") - pl.col("_group_return")).alias("group_relative_return"),
            *[
                (pl.col(f"_trend{window}") - pl.col(f"market_trend{window}")).alias(f"relative_trend{window}")
                for window in (5, 20)
            ],
        )
        .with_columns(
            (pl.col("market_shock") * pl.col("relative_return")).alias("shock_x_relative"),
            (pl.col("market_return").clip(upper_bound=0).abs() * pl.col("relative_return")).alias("down_x_relative"),
            (pl.col("amount_spread") * (pl.col("amount_rank20") - 0.5)).alias("spread_x_amount_rank"),
            ((pl.col("market_amount_ratio") - 1) * (pl.col("stock_amount_ratio") - 1)).alias("amount_x_stock_amount"),
        )
    )
    features = panel.select(
        *keys,
        *[
            pl.when(pl.col(name).is_finite()).then(pl.col(name)).alias(PREFIX + name)
            for names in GROUPS.values()
            for name in names
        ],
    )
    daily = daily.drop("_market_vol20", "_market_mean20", "_market_amount20")
    return features, daily


def context_protocol() -> dict:
    """Publish the information set and feature grouping for reproducible research."""
    return {
        "feature_groups": {name: list(columns) for name, columns in FEATURE_GROUPS.items()},
        "signal_time": "T close; no forward labels or future tradability used",
        "market_pool": "SH/SZ quoted positive-volume/amount rows with finite adjacent-calendar adjusted return; includes limit stocks",
        "amount_group": "daily historical-amount average-rank thirds; 20 calendar trading days through T-1, min 10; suspension amount=0; ties stay together",
        "amount_unit": "unchanged Tushare daily.amount; ratios/ranks are unitless; not market capitalization",
        "amount_concentration": "current amount in average-rank top ceil(10% of market pool) divided by pool amount; ties may alter selected count",
        "market_trend": "compound equal-weight market returns over 5/20 trading days",
        "market_shock": "(current market return - prior20 mean)/prior20 sample std; min10",
        "relative_return": "stock adjusted return minus contemporaneous equal-weight market/group return",
        "common_context_diagnostic": "daily-constant context has no single-factor cross-sectional IC; evaluate by model ablation",
    }
