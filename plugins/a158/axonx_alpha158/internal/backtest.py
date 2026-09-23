"""Pure portfolio calculations for Alpha158 prediction backtests."""

from __future__ import annotations

import math
from dataclasses import dataclass

import polars as pl

TOP_NS = (1, 2, 3, 5, 10, 15, 20, 30)
HOLDING_DETAIL_TOP_N = 30


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    transaction_cost_rate: float
    annual_risk_free_rate: float
    annualization_days: int
    minimum_index_weight_coverage: float
    index_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BacktestResult:
    daily: pl.DataFrame
    summary: pl.DataFrame
    benchmark_keys: tuple[str, ...]


def run_backtest(
    frame: pl.DataFrame,
    index_columns: tuple[str, ...],
    config: BacktestConfig,
) -> BacktestResult:
    """Validate predictions and calculate daily and period-level results."""
    _validate_predictions(frame, index_columns)
    available_indices = {
        column.removeprefix("index_weight_").lower(): column for column in index_columns
    }
    unknown = [code for code in config.index_codes if code not in available_indices]
    if unknown:
        available = ", ".join(sorted(available_indices)) or "无"
        raise ValueError(
            f"预测文件没有指数权重列: {', '.join(unknown)}；可选指数: {available}"
        )

    candidate_filter = pl.col("is_buyable") & pl.col("pred").is_not_null()
    if config.index_codes:
        candidate_filter &= pl.any_horizontal(
            *(pl.col(available_indices[code]) > 0 for code in config.index_codes)
        )
    settled_dates = frame.filter("label_valid").select("trade_date").unique()
    candidates = frame.filter(candidate_filter).join(settled_dates, on="trade_date", how="inner")
    if candidates.is_empty():
        raise ValueError("预测文件没有可回测的可买样本")
    candidates = candidates.sort("trade_date", "pred", "ts_code", descending=(False, True, False)).with_columns(
        pl.col("ts_code").cum_count().over("trade_date").alias("rank")
    )
    if candidates.filter(
        (pl.col("rank") <= max(TOP_NS)) & pl.col("entry_is_buyable") & ~pl.col("label_valid")
    ).height:
        raise ValueError("目标股票已开盘买入，但缺少下一交易日开盘价；无法可靠结算回测")
    if candidates.filter(
        (pl.col("rank") <= max(TOP_NS)) & pl.col("entry_is_buyable") & ~pl.col("exit_is_sellable")
    ).height:
        raise ValueError("目标股票在退出日开盘无法卖出；单日收益模型无法可靠结算回测")
    candidates = _enrich_candidates(candidates)

    daily = candidates.group_by("trade_date").agg(
        pl.len().alias("candidate_count"),
        _correlation("pearson", "ic"),
        _correlation("spearman", "rank_ic"),
    )
    universe = (
        frame.filter(pl.col("label_valid") & pl.col("actual_return").is_not_null())
        .group_by("trade_date")
        .agg(pl.col("actual_return").mean().alias("benchmark_universe_return"))
    )
    dates = candidates.group_by("trade_date").agg(
        pl.col("entry_date").drop_nulls().first().alias("entry_date"),
        pl.col("exit_date").drop_nulls().first().alias("exit_date"),
    )
    daily = daily.join(dates, on="trade_date", how="left").join(universe, on="trade_date", how="left")
    indices = _index_benchmarks(
        frame,
        index_columns,
        config.minimum_index_weight_coverage,
    )
    if indices is not None:
        daily = daily.join(indices, on="trade_date", how="left")
    for portfolio in pl.collect_all(
        [
            _portfolio_daily(candidates, top_n, config.transaction_cost_rate).lazy()
            for top_n in TOP_NS
        ]
    ):
        daily = daily.join(portfolio, on="trade_date", how="left")
    daily = daily.join(_holding_details(candidates), on="trade_date", how="left").sort(
        "trade_date"
    )
    if daily.filter(
        pl.any_horizontal(pl.col(*(f"top{top_n}_net_return" for top_n in TOP_NS)) <= -1)
    ).height:
        raise ValueError("扣费后收益不能低于 -100%")

    benchmark_keys = ("universe",) + tuple(
        column.removeprefix("index_weight_") for column in index_columns
    )
    summary = _summarize(
        daily,
        benchmark_keys,
        config.annual_risk_free_rate,
        config.annualization_days,
    )
    return BacktestResult(daily, summary, benchmark_keys)


def _validate_predictions(
    frame: pl.DataFrame,
    index_columns: tuple[str, ...],
) -> None:
    if frame.is_empty():
        raise ValueError("预测文件为空")
    if frame.select("trade_date", "ts_code").n_unique() != frame.height:
        raise ValueError("预测文件包含重复的 trade_date, ts_code")
    if frame.filter(
        pl.col("trade_date").str.to_date("%Y%m%d", strict=False).is_null()
    ).height:
        raise ValueError("trade_date 必须是有效 YYYYMMDD")
    if frame.filter(
        pl.any_horizontal(
            pl.col("pred", "actual_return").is_not_null()
            & ~pl.col("pred", "actual_return").is_finite()
        )
    ).height:
        raise ValueError("pred 或 actual_return 包含非有限值")
    if frame.filter(
        pl.col("label_valid")
        & (pl.col("actual_return").is_null() | (pl.col("actual_return") <= -1))
    ).height:
        raise ValueError("有效 actual_return 必须非空且大于 -1")
    for column in index_columns:
        weight = pl.col(column)
        if frame.filter(
            weight.is_not_null() & (~weight.is_finite() | (weight < 0))
        ).height:
            raise ValueError(f"{column} 必须是非负有限小数权重")
        if frame.group_by("trade_date").agg(weight.sum()).filter(weight > 1.05).height:
            raise ValueError(f"{column} 每日合计不能明显超过 1")


def _correlation(method: str, name: str) -> pl.Expr:
    return (
        pl.corr("pred", "actual_return", method=method)
        .fill_nan(0)
        .fill_null(0)
        .alias(name)
    )


def _enrich_candidates(candidates: pl.DataFrame) -> pl.DataFrame:
    ranked = candidates
    ideal = (
        ranked.filter("label_valid").sort(
            "trade_date", "actual_return", "ts_code", descending=(False, True, False)
        )
        .with_columns(
            pl.col("ts_code").cum_count().over("trade_date").alias("ideal_rank")
        )
        .select("trade_date", "ts_code", "ideal_rank")
    )
    count = pl.col("actual_return").is_not_null().sum().over("trade_date")
    actual_rank = pl.col("actual_return").rank(method="average").over("trade_date")
    return ranked.join(ideal, on=("trade_date", "ts_code"), how="left").with_columns(
        pl.when(count > 1)
        .then((actual_rank - 1) / (count - 1))
        .otherwise(1.0)
        .alias("relevance")
    )


def _index_benchmarks(
    frame: pl.DataFrame,
    index_columns: tuple[str, ...],
    minimum_coverage: float,
) -> pl.DataFrame | None:
    expressions: list[pl.Expr] = []
    for column in index_columns:
        key = column.removeprefix("index_weight_")
        valid = (
            pl.col("label_valid")
            & pl.col("actual_return").is_not_null()
            & pl.col(column).is_not_null()
        )
        covered = pl.col(column).filter(valid).sum()
        expressions.extend(
            (
                covered.clip(upper_bound=1).alias(f"benchmark_{key}_coverage"),
                pl.when(covered >= minimum_coverage)
                .then(
                    (pl.col(column) * pl.col("actual_return")).filter(valid).sum()
                    / covered
                )
                .alias(f"benchmark_{key}_return"),
            )
        )
    return frame.group_by("trade_date").agg(*expressions) if expressions else None


def _portfolio_daily(
    candidates: pl.DataFrame,
    top_n: int,
    cost_rate: float,
) -> pl.DataFrame:
    prefix = f"top{top_n}"
    selected = candidates.filter(pl.col("rank") <= top_n).with_columns(
        pl.when("entry_is_buyable").then(1 / pl.len().over("trade_date")).otherwise(0).alias("weight")
    )
    dates = (
        selected.select("trade_date").unique().sort("trade_date").with_row_index("_day")
    )
    weights = selected.join(dates, on="trade_date").select(
        "_day", "trade_date", "ts_code", "weight", "actual_return", "rank", "relevance"
    )
    previous = weights.select(
        (pl.col("_day") + 1).alias("_day"),
        "ts_code",
        pl.col("weight").alias("_previous_weight"),
    )
    previous_invested = weights.group_by("_day").agg(
        pl.col("weight").sum().alias("_previous_invested")
    ).with_columns((pl.col("_day") + 1).alias("_day"))
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
            (pl.col("actual_return").fill_null(0) * pl.col("weight"))
            .sum()
            .alias(f"{prefix}_gross_return"),
            (gain / (pl.col("rank") + 1).log(2)).sum().alias("_dcg"),
            pl.when(pl.col("_previous_weight").is_not_null())
            .then(pl.min_horizontal("weight", "_previous_weight"))
            .otherwise(0)
            .sum()
            .alias("_overlap"),
            pl.col("weight").sum().alias("_invested"),
        )
        .join(idcg, on="trade_date")
        .join(previous_invested, on="_day", how="left")
        .sort("_day")
        .with_columns(
            (pl.max_horizontal("_invested", pl.col("_previous_invested").fill_null(0)) - pl.col("_overlap").fill_null(0)).alias(f"{prefix}_turnover"),
            pl.when(pl.col("_idcg") > 0)
            .then(pl.col("_dcg") / pl.col("_idcg"))
            .otherwise(0.0)
            .alias(f"{prefix}_ndcg"),
        )
        .with_columns(
            (pl.col(f"{prefix}_turnover") * cost_rate).alias(
                f"{prefix}_transaction_cost"
            )
        )
        .with_columns(
            (
                pl.col(f"{prefix}_gross_return") - pl.col(f"{prefix}_transaction_cost")
            ).alias(f"{prefix}_net_return")
        )
        .drop("_day", "_dcg", "_idcg", "_overlap", "_invested", "_previous_invested")
    )


def _holding_details(candidates: pl.DataFrame) -> pl.DataFrame:
    selected = (
        candidates.filter(pl.col("rank") <= HOLDING_DETAIL_TOP_N)
        .with_columns(
            pl.when("entry_is_buyable").then(1 / pl.len().over("trade_date")).otherwise(0).alias("weight"),
            pl.col("pred").alias("prediction"),
            pl.col("actual_return").alias("daily_return"),
        )
        .sort("trade_date", "rank")
    )
    return selected.group_by("trade_date", maintain_order=True).agg(
        pl.struct(
            "rank", "ts_code", "name", "prediction", "daily_return", "weight"
        ).alias("top30_holdings")
    )


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
        return pl.col("exit_date").str.slice(0, 4)
    if period_type == "quarter":
        month = pl.col("exit_date").str.slice(4, 2).cast(pl.Int8)
        return (
            pl.col("exit_date").str.slice(0, 4)
            + "Q"
            + (((month - 1) // 3) + 1).cast(pl.String)
        )
    return (
        pl.col("exit_date").str.slice(0, 4)
        + "-"
        + pl.col("exit_date").str.slice(4, 2)
    )


def _summarize(
    daily: pl.DataFrame,
    benchmark_keys: tuple[str, ...],
    annual_risk_free_rate: float,
    annualization_days: int,
) -> pl.DataFrame:
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
        "_period", "exit_date"
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
        pl.col("exit_date").min().alias("period_start"),
        pl.col("exit_date").max().alias("period_end"),
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
                ((pl.col(f"{prefix}_gross_return") + 1).product() - 1).alias(
                    f"{prefix}_gross_cumulative_return"
                ),
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
