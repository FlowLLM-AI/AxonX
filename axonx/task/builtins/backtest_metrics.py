"""Period-level metrics for backtest results."""

import math

import polars as pl

from .backtest_portfolio import TOP_NS


def _ratio(column: str) -> pl.Expr:
    values = pl.col(column).drop_nulls()
    std = values.std(ddof=1)
    return (
        pl.when((values.len() > 1) & (std > 0)).then(values.mean() / std).otherwise(0.0)
    )


def _period_column(period_type: str) -> pl.Expr:
    if period_type == "overall":
        return pl.lit("all")
    if period_type == "year":
        return pl.col("trade_date").str.slice(0, 4)
    if period_type == "quarter":
        month = pl.col("trade_date").str.slice(4, 2).cast(pl.Int8)
        return (
            pl.col("trade_date").str.slice(0, 4)
            + "Q"
            + (((month - 1) // 3) + 1).cast(pl.String)
        )
    return (
        pl.col("trade_date").str.slice(0, 4)
        + "-"
        + pl.col("trade_date").str.slice(4, 2)
    )


def summarize(
    daily: pl.DataFrame,
    benchmark_keys: tuple[str, ...],
    annual_risk_free_rate: float,
    annualization_days: int,
) -> pl.DataFrame:
    """Combine overall, yearly, quarterly, and monthly backtest summaries."""
    return pl.concat(
        [
            _summarize_period(
                daily,
                period_type,
                benchmark_keys,
                annual_risk_free_rate,
                annualization_days,
            )
            for period_type in ("overall", "year", "quarter", "month")
        ],
        how="vertical",
    )


def _summarize_period(
    daily: pl.DataFrame,
    period_type: str,
    benchmark_keys: tuple[str, ...],
    annual_risk_free_rate: float,
    annualization_days: int,
) -> pl.DataFrame:
    daily_rf = (1 + annual_risk_free_rate) ** (1 / annualization_days) - 1
    frame = daily.with_columns(_period_column(period_type).alias("_period")).sort(
        "_period", "trade_date"
    )
    derived: list[pl.Expr] = []
    for top_n in TOP_NS:
        prefix = f"top{top_n}"
        derived.extend(
            (
                (pl.col(f"{prefix}_net_return") + 1)
                .cum_prod()
                .over("_period")
                .alias(f"_{prefix}_equity"),
                (pl.col(f"{prefix}_gross_return") - daily_rf).alias(
                    f"_{prefix}_gross_excess"
                ),
            )
        )
        derived.extend(
            (
                pl.col(f"{prefix}_gross_return") - pl.col(f"benchmark_{key}_return")
            ).alias(f"_{prefix}_{key}_active")
            for key in benchmark_keys
        )
    frame = frame.with_columns(*derived)
    annual_scale = math.sqrt(annualization_days)
    metrics: list[pl.Expr] = [
        pl.col("trade_date").min().alias("period_start"),
        pl.col("trade_date").max().alias("period_end"),
        pl.len().alias("trading_days"),
        pl.col("ic").mean().alias("ic_mean"),
        (_ratio("ic") * annual_scale).alias("icir"),
        pl.col("rank_ic").mean().alias("rank_ic_mean"),
        (_ratio("rank_ic") * annual_scale).alias("rank_icir"),
    ]
    for top_n in TOP_NS:
        prefix = f"top{top_n}"
        net = f"{prefix}_net_return"
        equity = f"_{prefix}_equity"
        cumulative = (pl.col(net) + 1).product()
        peak = pl.max_horizontal(pl.lit(1.0), pl.col(equity).cum_max().over("_period"))
        metrics.extend(
            (
                (cumulative - 1).alias(f"{prefix}_net_cumulative_return"),
                pl.when(cumulative > 0)
                .then(cumulative.pow(annualization_days / pl.len()) - 1)
                .otherwise(-1.0)
                .alias(f"{prefix}_net_annualized_return"),
                (pl.col(net).std(ddof=1) * annual_scale).alias(
                    f"{prefix}_net_annualized_volatility"
                ),
                (pl.col(equity) / peak - 1).min().alias(f"{prefix}_net_max_drawdown"),
                (pl.col(net) > 0).mean().alias(f"{prefix}_net_win_rate"),
                pl.col(f"{prefix}_turnover").mean().alias(f"{prefix}_average_turnover"),
                pl.col(f"{prefix}_gross_return")
                .sum()
                .alias(f"{prefix}_gross_cumulative_return"),
                (_ratio(f"_{prefix}_gross_excess") * annual_scale).alias(
                    f"{prefix}_gross_sharpe"
                ),
            )
        )
        metrics.extend(
            (_ratio(f"_{prefix}_{key}_active") * annual_scale).alias(
                f"{prefix}_information_ratio_{key}"
            )
            for key in benchmark_keys
        )
    return (
        frame.group_by("_period", maintain_order=True)
        .agg(*metrics)
        .rename({"_period": "period"})
        .with_columns(pl.lit(period_type).alias("period_type"))
        .select("period_type", "period", pl.exclude("period_type", "period"))
    )
