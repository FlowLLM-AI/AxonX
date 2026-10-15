"""Daily diagnostics and period summaries derived from the stock execution ledger."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import polars as pl

from .data import KEYS, normalize_keys, validate_keys

if TYPE_CHECKING:
    from .engine import BacktestConfig


def daily_output(dates, daily, signals, targets, labels, as_of_date, config):
    """Assemble daily metrics and candidate diagnostics after execution."""
    daily_long = pl.DataFrame(daily)
    output = pl.DataFrame({"trade_date": dates})
    for n in config.top_ns:
        part = daily_long.filter(pl.col("top_n") == n).drop("top_n")
        output = output.join(
            part.rename({c: f"top{n}_{c}" for c in part.columns if c != "trade_date"}),
            on="trade_date",
            validate="1:1",
        )
    diagnostics, benchmarks = _diagnostics(signals, targets, labels, as_of_date, config)
    output = output.join(diagnostics, on="trade_date", how="left").with_columns(
        pl.col("ic", "rank_ic").cast(pl.Float64)
    )
    if labels is not None:
        target_labels = (
            normalize_keys(labels)
            .filter(pl.col("label_valid") & (pl.col("label_target_date").cast(pl.String) <= as_of_date))
            .select(*KEYS, pl.col("label_return").alias("_target_return"))
        )
        targets = targets.join(target_labels, on=list(KEYS), how="left", validate="1:1")
    else:
        targets = targets.with_columns(pl.lit(None, dtype=pl.Float64).alias("_target_return"))
    details = targets.group_by("trade_date").agg(
        pl.len().alias("candidate_count"),
        pl.struct(
            pl.col("target_rank").alias("rank"),
            "ts_code",
            (pl.col("name") if "name" in targets.columns else pl.col("ts_code").alias("name")),
            pl.col("pred").alias("prediction"),
            pl.col("_target_return").alias("daily_return"),
            (1.0 / pl.min_horizontal(pl.len(), pl.lit(30))).alias("weight"),
        )
        .filter(pl.col("target_rank") <= 30)
        .alias("top30_holdings"),
    )
    output = output.join(details, on="trade_date", how="left").with_columns(pl.col("candidate_count").fill_null(0))
    return output, targets, benchmarks


def _diagnostics(
    signals: pl.DataFrame,
    candidates: pl.DataFrame,
    labels: pl.DataFrame | None,
    cutoff: str,
    config: BacktestConfig,
) -> tuple[pl.DataFrame, tuple[str, ...]]:
    dates = signals.select("trade_date").unique()
    if labels is None:
        return (
            dates.with_columns(
                pl.lit(None, dtype=pl.Float64).alias("ic"),
                pl.lit(None, dtype=pl.Float64).alias("rank_ic"),
                *(pl.lit(None, dtype=pl.Float64).alias(f"top{n}_ndcg") for n in config.top_ns),
            ),
            (),
        )
    labels = normalize_keys(labels)
    validate_keys(labels)
    joined = signals.join(labels, on=list(KEYS), how="left", validate="1:1").filter(
        pl.col("label_valid") & (pl.col("label_target_date").cast(pl.String) <= cutoff)
    )
    matured = candidates.join(joined.select(*KEYS, "label_return"), on=list(KEYS), how="inner", validate="1:1")
    diagnostics = matured.group_by("trade_date").agg(
        pl.corr("pred", "label_return").alias("ic"),
        pl.corr("pred", "label_return", method="spearman").alias("rank_ic"),
    )
    quality = []
    for key, data in matured.partition_by("trade_date", as_dict=True).items():
        actual = data["label_return"]
        relevance = (actual.rank(method="average") / len(actual)).to_list()
        rows = list(zip(data["target_rank"].to_list(), relevance, strict=True))
        ideal = sorted(relevance, reverse=True)
        row = {"trade_date": key[0]}
        for n in config.top_ns:
            dcg = sum((2**v - 1) / math.log2(rank + 1) for rank, v in rows if rank <= n)
            idcg = sum((2**v - 1) / math.log2(rank + 2) for rank, v in enumerate(ideal[:n]))
            row[f"top{n}_ndcg"] = dcg / idcg if idcg else None
        quality.append(row)
    schema = {
        "trade_date": pl.String,
        **{f"top{n}_ndcg": pl.Float64 for n in config.top_ns},
    }
    diagnostics = diagnostics.join(
        pl.DataFrame(quality, schema=schema), on="trade_date", how="full", coalesce=True
    ).with_columns(pl.when(pl.col(c).is_finite()).then(pl.col(c)).otherwise(None).alias(c) for c in ("ic", "rank_ic"))
    weights = [c for c in signals.columns if c.startswith("index_weight_")]
    benchmarks = ("universe", *(c.removeprefix("index_weight_") for c in weights))
    returns = (
        joined.group_by("label_target_date")
        .agg(
            pl.col("label_return").mean().alias("benchmark_universe_return"),
            *(
                pl.when(pl.col(c).sum() >= config.minimum_index_weight_coverage)
                .then((pl.col(c) * pl.col("label_return")).sum() / pl.col(c).sum())
                .alias(f"benchmark_{c.removeprefix('index_weight_')}_return")
                for c in weights
            ),
        )
        .rename({"label_target_date": "trade_date"})
    )
    # Signal diagnostics and valuation-period benchmarks have different date axes.
    return (
        dates.join(diagnostics, on="trade_date", how="left").join(returns, on="trade_date", how="full", coalesce=True),
        benchmarks,
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
    top_ns: tuple[int, ...],
) -> pl.DataFrame:
    return pl.concat(
        [
            _summarize_period(
                daily,
                period_type,
                benchmark_keys,
                annual_risk_free_rate,
                annualization_days,
                top_ns,
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
    top_ns: tuple[int, ...],
) -> pl.DataFrame:
    daily_rf = (1 + annual_risk_free_rate) ** (1 / annualization_days) - 1
    frame = daily.with_columns(_period_column(period_type).alias("_period")).sort(
        "_period",
        "trade_date",
    )
    derived: list[pl.Expr] = []
    for top_n in top_ns:
        prefix = f"top{top_n}"
        derived.extend(
            (
                (pl.col(f"{prefix}_net_return") + 1).cum_prod().over("_period").alias(f"_{prefix}_equity"),
                (pl.col(f"{prefix}_gross_return") - daily_rf).alias(
                    f"_{prefix}_gross_excess",
                ),
            ),
        )
        derived.extend(
            (pl.col(f"{prefix}_gross_return") - pl.col(f"benchmark_{key}_return")).alias(f"_{prefix}_{key}_active")
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
    for top_n in top_ns:
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
                    f"{prefix}_net_annualized_volatility",
                ),
                (pl.col(equity) / peak - 1).min().alias(f"{prefix}_net_max_drawdown"),
                (pl.col(net) > 0).mean().alias(f"{prefix}_net_win_rate"),
                pl.col(f"{prefix}_turnover").mean().alias(f"{prefix}_average_turnover"),
                pl.col(f"{prefix}_delayed_exits").sum().alias(f"{prefix}_delayed_exits"),
                pl.col(f"{prefix}_unsettled_positions").last().alias(f"{prefix}_unsettled_positions"),
                ((pl.col(f"{prefix}_gross_return") + 1).product() - 1).alias(
                    f"{prefix}_gross_cumulative_return",
                ),
                (_ratio(f"_{prefix}_gross_excess") * annual_scale).alias(
                    f"{prefix}_gross_sharpe",
                ),
            ),
        )
        metrics.extend(
            (_ratio(f"_{prefix}_{key}_active") * annual_scale).alias(
                f"{prefix}_information_ratio_{key}",
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
