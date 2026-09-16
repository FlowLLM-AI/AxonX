"""Pure calculations for the Alpha158 backtest artifact protocol."""

from __future__ import annotations

import math

import polars as pl

TOP_NS = (1, 2, 3, 5, 10, 15, 20, 30)
HOLDING_DETAIL_TOP_N = 30


def correlation(method: str, name: str) -> pl.Expr:
    return pl.corr("pred", "actual_return", method=method).fill_nan(0).fill_null(0).alias(name)


def enrich_candidates(candidates: pl.DataFrame) -> pl.DataFrame:
    """Add prediction rank, robust relevance, and the ideal return rank."""
    ranked = candidates.sort("trade_date", "pred", "ts_code", descending=(False, True, False)).with_columns(
        pl.col("ts_code").cum_count().over("trade_date").alias("rank"),
    )
    ideal = (
        ranked.sort("trade_date", "actual_return", "ts_code", descending=(False, True, False))
        .with_columns(pl.col("ts_code").cum_count().over("trade_date").alias("ideal_rank"))
        .select("trade_date", "ts_code", "ideal_rank")
    )
    count = pl.len().over("trade_date")
    actual_rank = pl.col("actual_return").rank(method="average").over("trade_date")
    return ranked.join(ideal, on=("trade_date", "ts_code")).with_columns(
        pl.when(count > 1).then((actual_rank - 1) / (count - 1)).otherwise(1.0).alias("relevance"),
    )


def index_benchmarks(
    frame: pl.DataFrame,
    index_columns: tuple[str, ...],
    minimum_coverage: float,
) -> pl.DataFrame | None:
    expressions: list[pl.Expr] = []
    for column in index_columns:
        key = column.removeprefix("index_weight_")
        valid = pl.col("label_valid") & pl.col("actual_return").is_not_null() & pl.col(column).is_not_null()
        covered = pl.col(column).filter(valid).sum()
        expressions.extend(
            (
                covered.clip(upper_bound=1).alias(f"benchmark_{key}_coverage"),
                pl.when(covered >= minimum_coverage)
                .then((pl.col(column) * pl.col("actual_return")).filter(valid).sum() / covered)
                .alias(f"benchmark_{key}_return"),
            ),
        )
    return frame.group_by("trade_date").agg(*expressions) if expressions else None


def portfolio_daily(candidates: pl.DataFrame, top_n: int, cost_rate: float) -> pl.DataFrame:
    prefix = f"top{top_n}"
    selected = candidates.filter(pl.col("rank") <= top_n).with_columns(
        (1 / pl.len().over("trade_date")).alias("weight"),
    )
    dates = selected.select("trade_date").unique().sort("trade_date").with_row_index("_day")
    weights = selected.join(dates, on="trade_date").select(
        "_day", "trade_date", "ts_code", "weight", "actual_return", "rank", "relevance",
    )
    previous = weights.select(
        (pl.col("_day") + 1).alias("_day"),
        "ts_code",
        pl.col("weight").alias("_previous_weight"),
    )
    gain = pl.lit(2.0).pow(pl.col("relevance")) - 1
    idcg = (
        candidates.filter(pl.col("ideal_rank") <= top_n)
        .group_by("trade_date")
        .agg((gain / (pl.col("ideal_rank") + 1).log(2)).sum().alias("_idcg"))
    )
    return (
        weights.join(previous, on=("_day", "ts_code"), how="left")
        .group_by("_day", "trade_date")
        .agg(
            pl.len().alias(f"{prefix}_count"),
            (pl.col("actual_return") * pl.col("weight")).sum().alias(f"{prefix}_gross_return"),
            (gain / (pl.col("rank") + 1).log(2)).sum().alias("_dcg"),
            pl.when(pl.col("_previous_weight").is_not_null())
            .then(pl.min_horizontal("weight", "_previous_weight"))
            .otherwise(0)
            .sum()
            .alias("_overlap"),
        )
        .join(idcg, on="trade_date")
        .sort("_day")
        .with_columns(
            pl.when(pl.col("_day") == 0)
            .then(0.0)
            .otherwise(1 - pl.col("_overlap").fill_null(0))
            .alias(f"{prefix}_turnover"),
            pl.when(pl.col("_idcg") > 0).then(pl.col("_dcg") / pl.col("_idcg")).otherwise(0.0).alias(
                f"{prefix}_ndcg",
            ),
        )
        .with_columns(
            (pl.col(f"{prefix}_turnover") * cost_rate).alias(f"{prefix}_transaction_cost"),
        )
        .with_columns(
            (pl.col(f"{prefix}_gross_return") - pl.col(f"{prefix}_transaction_cost")).alias(
                f"{prefix}_net_return",
            ),
        )
        .drop("_day", "_dcg", "_idcg", "_overlap")
    )


def holding_details(candidates: pl.DataFrame) -> pl.DataFrame:
    selected = (
        candidates.filter(pl.col("rank") <= HOLDING_DETAIL_TOP_N)
        .with_columns(
            (1 / pl.len().over("trade_date")).alias("weight"),
            pl.col("pred").alias("prediction"),
            pl.col("actual_return").alias("daily_return"),
        )
        .sort("trade_date", "rank")
    )
    return selected.group_by("trade_date", maintain_order=True).agg(
        pl.struct("rank", "ts_code", "name", "prediction", "daily_return", "weight").alias("top30_holdings"),
    )


def _ratio(column: str) -> pl.Expr:
    values = pl.col(column).drop_nulls()
    std = values.std(ddof=1)
    return pl.when((values.len() > 1) & (std > 0)).then(values.mean() / std).otherwise(0.0)


def _period_column(period_type: str) -> pl.Expr:
    if period_type == "overall":
        return pl.lit("all")
    if period_type == "year":
        return pl.col("trade_date").str.slice(0, 4)
    if period_type == "quarter":
        month = pl.col("trade_date").str.slice(4, 2).cast(pl.Int8)
        return pl.col("trade_date").str.slice(0, 4) + "Q" + (((month - 1) // 3) + 1).cast(pl.String)
    return pl.col("trade_date").str.slice(0, 4) + "-" + pl.col("trade_date").str.slice(4, 2)


def summarize(
    daily: pl.DataFrame,
    benchmark_keys: tuple[str, ...],
    annual_risk_free_rate: float,
    annualization_days: int,
) -> pl.DataFrame:
    frames = [
        _summarize_period(daily, period_type, benchmark_keys, annual_risk_free_rate, annualization_days)
        for period_type in ("overall", "year", "quarter", "month")
    ]
    return pl.concat(frames, how="vertical")


def _summarize_period(
    daily: pl.DataFrame,
    period_type: str,
    benchmark_keys: tuple[str, ...],
    annual_risk_free_rate: float,
    annualization_days: int,
) -> pl.DataFrame:
    daily_rf = (1 + annual_risk_free_rate) ** (1 / annualization_days) - 1
    frame = daily.with_columns(_period_column(period_type).alias("_period")).sort("_period", "trade_date")
    derived: list[pl.Expr] = []
    for top_n in TOP_NS:
        prefix = f"top{top_n}"
        derived.extend(
            (
                (pl.col(f"{prefix}_net_return") + 1).cum_prod().over("_period").alias(f"_{prefix}_equity"),
                (pl.col(f"{prefix}_gross_return") - daily_rf).alias(f"_{prefix}_gross_excess"),
            ),
        )
        derived.extend(
            (pl.col(f"{prefix}_gross_return") - pl.col(f"benchmark_{key}_return")).alias(
                f"_{prefix}_{key}_active",
            )
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
                (pl.col(net).std(ddof=1) * annual_scale).alias(f"{prefix}_net_annualized_volatility"),
                (pl.col(equity) / peak - 1).min().alias(f"{prefix}_net_max_drawdown"),
                (pl.col(net) > 0).mean().alias(f"{prefix}_net_win_rate"),
                pl.col(f"{prefix}_turnover").mean().alias(f"{prefix}_average_turnover"),
                pl.col(f"{prefix}_gross_return").sum().alias(f"{prefix}_gross_cumulative_return"),
                (_ratio(f"_{prefix}_gross_excess") * annual_scale).alias(f"{prefix}_gross_sharpe"),
            ),
        )
        metrics.extend(
            (_ratio(f"_{prefix}_{key}_active") * annual_scale).alias(f"{prefix}_information_ratio_{key}")
            for key in benchmark_keys
        )
    return (
        frame.group_by("_period", maintain_order=True)
        .agg(*metrics)
        .rename({"_period": "period"})
        .with_columns(pl.lit(period_type).alias("period_type"))
        .select("period_type", "period", pl.exclude("period_type", "period"))
    )
