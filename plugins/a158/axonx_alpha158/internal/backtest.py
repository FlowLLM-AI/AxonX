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
    frame = frame.with_columns(pl.col("entry_date", "exit_date").cast(pl.String))
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
    candidates = frame.filter(candidate_filter)
    if candidates.is_empty():
        raise ValueError("预测文件没有可回测的可买样本")
    candidates = candidates.sort("trade_date", "pred", "ts_code", descending=(False, True, False)).with_columns(
        pl.col("ts_code").cum_count().over("trade_date").alias("rank")
    )
    candidates = _enrich_candidates(candidates)
    top_candidates = candidates.filter(pl.col("rank") <= max(TOP_NS))
    strict_diagnostics = candidates.filter(
        pl.col("label_valid") & ~pl.col("exit_delayed")
        & ((pl.col("rank") <= max(TOP_NS)) | (pl.col("ideal_rank") <= max(TOP_NS)))
    )

    diagnostics = candidates.filter(pl.col("label_valid") & ~pl.col("exit_delayed")).group_by("trade_date").agg(
        _correlation("pearson", "ic"),
        _correlation("spearman", "rank_ic"),
    )
    signals = candidates.group_by("trade_date").agg(
        pl.len().alias("candidate_count"),
        pl.col("entry_date").drop_nulls().first().alias("entry_date"),
        pl.when(pl.col("exit_date").n_unique() == 1)
        .then(pl.col("exit_date").first())
        .alias("exit_date"),
    )
    calendar = sorted(
        set(candidates["trade_date"].unique().to_list())
        | set(top_candidates["entry_date"].drop_nulls().to_list())
        | set(top_candidates["exit_date"].drop_nulls().to_list())
        | set(frame.filter(pl.col("label_valid") & ~pl.col("exit_delayed"))["exit_date"].drop_nulls().unique().to_list())
    )
    daily = pl.DataFrame({"trade_date": calendar}).join(signals, on="trade_date", how="left").join(
        diagnostics, on="trade_date", how="left"
    ).with_columns(pl.col("candidate_count").fill_null(0))
    universe = (
        frame.filter(pl.col("label_valid") & ~pl.col("exit_delayed") & pl.col("actual_return").is_not_null())
        .group_by("exit_date")
        .agg(pl.col("actual_return").mean().alias("benchmark_universe_return"))
        .rename({"exit_date": "trade_date"})
    )
    daily = daily.join(universe, on="trade_date", how="left")
    indices = _index_benchmarks(
        frame,
        index_columns,
        config.minimum_index_weight_coverage,
    )
    if indices is not None:
        daily = daily.join(indices, on="trade_date", how="left")
    for top_n in TOP_NS:
        daily = daily.join(
            _portfolio_daily(top_candidates, strict_diagnostics, calendar, top_n, config.transaction_cost_rate),
            on="trade_date", how="left",
        )
    daily = daily.join(_holding_details(top_candidates), on="trade_date", how="left").sort(
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
    if frame.filter(
        pl.col("label_valid")
        & (pl.col("entry_date").is_null() | pl.col("exit_date").is_null() | (pl.col("exit_date") <= pl.col("entry_date")))
    ).height:
        raise ValueError("有效收益必须有晚于买入日的实际退出日期")
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
        ranked.filter(pl.col("label_valid") & ~pl.col("exit_delayed")).sort(
            "trade_date", "actual_return", "ts_code", descending=(False, True, False)
        )
        .with_columns(
            pl.col("ts_code").cum_count().over("trade_date").alias("ideal_rank")
        )
        .select("trade_date", "ts_code", "ideal_rank")
    )
    strict_return = pl.when(pl.col("label_valid") & ~pl.col("exit_delayed")).then(pl.col("actual_return"))
    count = strict_return.is_not_null().sum().over("trade_date")
    actual_rank = strict_return.rank(method="average").over("trade_date")
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
            & ~pl.col("exit_delayed")
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
    return frame.group_by("exit_date").agg(*expressions).rename({"exit_date": "trade_date"}) if expressions else None


def _portfolio_daily(
    candidates: pl.DataFrame,
    strict_diagnostics: pl.DataFrame,
    calendar: list[str],
    top_n: int,
    cost_rate: float,
) -> pl.DataFrame:
    """Book returns on actual exit dates while capital stays locked in positions."""
    prefix = f"top{top_n}"
    entry_events: dict[str, list[dict]] = {}
    signal_rows: dict[str, list[dict]] = {}
    for row in candidates.filter(pl.col("rank") <= top_n).to_dicts():
        if row["entry_date"] is not None:
            entry_events.setdefault(row["entry_date"], []).append(row)
    for row in strict_diagnostics.filter(
        (pl.col("rank") <= top_n) | (pl.col("ideal_rank") <= top_n)
    ).to_dicts():
        signal_rows.setdefault(row["trade_date"], []).append(row)

    cash = 1.0
    positions: list[dict] = []
    records: list[dict] = []

    def gain(row: dict) -> float:
        return 2 ** row["relevance"] - 1 if row["relevance"] is not None else 0.0

    for date in calendar:
        opening_equity = cash + sum(position["principal"] for position in positions)
        if opening_equity <= 0:
            raise ValueError("组合权益必须大于零")
        exiting = [position for position in positions if position["exit_date"] == date]
        positions = [position for position in positions if position["exit_date"] != date]
        sold_principal = sum(position["principal"] for position in exiting)
        realized_profit = sum(position["principal"] * position["actual_return"] for position in exiting)
        cash += sold_principal + realized_profit

        available = max(cash - cost_rate * (cash + sum(position["principal"] for position in positions)), 0.0)
        target_principal = max(cash + sum(position["principal"] for position in positions), 0.0) * (1 - cost_rate) / top_n
        bought = 0.0
        unfilled = 0
        for row in entry_events.get(date, ()):
            if not row["entry_is_buyable"]:
                unfilled += 1
                continue
            if len(positions) >= top_n or any(position["ts_code"] == row["ts_code"] for position in positions):
                continue
            principal = min(target_principal, available)
            if principal <= 1e-12:
                continue
            if row["exit_date"] is not None and (not row["label_valid"] or row["actual_return"] is None):
                raise ValueError("已知退出日期的买入样本缺少有效收益")
            positions.append({**row, "principal": principal})
            cash -= principal
            available -= principal
            bought += principal

        traded = max(bought, sold_principal)
        cost_value = cost_rate * traded
        cash -= cost_value
        gross = realized_profit / opening_equity
        transaction_cost = cost_value / opening_equity
        strict = [row for row in signal_rows.get(date, ()) if row["label_valid"] and not row["exit_delayed"]]
        selected_strict = [row for row in strict if row["rank"] <= top_n]
        dcg = sum(gain(row) / math.log2(row["rank"] + 1) for row in selected_strict)
        idcg = sum(
            gain(row) / math.log2(row["ideal_rank"] + 1)
            for row in strict if row["ideal_rank"] is not None and row["ideal_rank"] <= top_n
        )
        records.append({
            "trade_date": date,
            f"{prefix}_count": len(positions),
            f"{prefix}_gross_return": gross,
            f"{prefix}_turnover": traded / opening_equity,
            f"{prefix}_transaction_cost": transaction_cost,
            f"{prefix}_net_return": gross - transaction_cost,
            f"{prefix}_ndcg": dcg / idcg if idcg > 0 else 0.0,
            f"{prefix}_open_positions": len(positions),
            f"{prefix}_delayed_open_positions": sum(bool(position["exit_delayed"]) for position in positions),
            f"{prefix}_unsettled_positions": sum(position["exit_date"] is None for position in positions),
            f"{prefix}_exits": len(exiting),
            f"{prefix}_delayed_exits": sum(bool(position["exit_delayed"]) for position in exiting),
            f"{prefix}_unfilled_entries": unfilled,
        })
    return pl.DataFrame(records)


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
            "rank", "ts_code", "name", "prediction", "daily_return", "weight", "entry_date", "exit_date", "exit_delayed"
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
                pl.col(f"{prefix}_delayed_exits").sum().alias(f"{prefix}_delayed_exits"),
                pl.col(f"{prefix}_unsettled_positions").last().alias(f"{prefix}_unsettled_positions"),
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
