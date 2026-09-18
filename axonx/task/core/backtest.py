"""Generate daily and summary Parquet backtest artifacts."""

from __future__ import annotations
import math
from collections.abc import Iterable
from pathlib import Path

import polars as pl
from pydantic import Field

from ...components.registry import R
from ...enums import TaskType
from ...utils.fs import atomic_write
from ..artifacts import read_metadata, artifact_path, artifact_record
from ..base import BaseInputParams, BaseOutputParams, BaseTask, TaskStep

TOP_NS = (1, 2, 3, 5, 10, 15, 20, 30)
HOLDING_DETAIL_TOP_N = 30


def correlation(method: str, name: str) -> pl.Expr:
    """Build a daily prediction and realized-return correlation expression."""
    return (
        pl.corr("pred", "actual_return", method=method)
        .fill_nan(0)
        .fill_null(0)
        .alias(name)
    )


def enrich_candidates(candidates: pl.DataFrame) -> pl.DataFrame:
    """Add prediction rank, robust relevance, and the ideal return rank."""
    ranked = candidates.sort(
        "trade_date", "pred", "ts_code", descending=(False, True, False)
    ).with_columns(
        pl.col("ts_code").cum_count().over("trade_date").alias("rank"),
    )
    ideal = (
        ranked.sort(
            "trade_date", "actual_return", "ts_code", descending=(False, True, False)
        )
        .with_columns(
            pl.col("ts_code").cum_count().over("trade_date").alias("ideal_rank")
        )
        .select("trade_date", "ts_code", "ideal_rank")
    )
    count = pl.len().over("trade_date")
    actual_rank = pl.col("actual_return").rank(method="average").over("trade_date")
    return ranked.join(ideal, on=("trade_date", "ts_code")).with_columns(
        pl.when(count > 1)
        .then((actual_rank - 1) / (count - 1))
        .otherwise(1.0)
        .alias("relevance"),
    )


def index_benchmarks(
    frame: pl.DataFrame,
    index_columns: tuple[str, ...],
    minimum_coverage: float,
) -> pl.DataFrame | None:
    """Calculate index-weighted benchmark returns and coverage by date."""
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
            ),
        )
    return frame.group_by("trade_date").agg(*expressions) if expressions else None


def portfolio_daily(
    candidates: pl.DataFrame, top_n: int, cost_rate: float
) -> pl.DataFrame:
    """Calculate daily return, turnover, and ranking metrics for a top-N portfolio."""
    prefix = f"top{top_n}"
    selected = candidates.filter(pl.col("rank") <= top_n).with_columns(
        (1 / pl.len().over("trade_date")).alias("weight"),
    )
    dates = (
        selected.select("trade_date").unique().sort("trade_date").with_row_index("_day")
    )
    weights = selected.join(dates, on="trade_date").select(
        "_day",
        "trade_date",
        "ts_code",
        "weight",
        "actual_return",
        "rank",
        "relevance",
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
            (pl.col("actual_return") * pl.col("weight"))
            .sum()
            .alias(f"{prefix}_gross_return"),
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
            pl.when(pl.col("_idcg") > 0)
            .then(pl.col("_dcg") / pl.col("_idcg"))
            .otherwise(0.0)
            .alias(
                f"{prefix}_ndcg",
            ),
        )
        .with_columns(
            (pl.col(f"{prefix}_turnover") * cost_rate).alias(
                f"{prefix}_transaction_cost"
            ),
        )
        .with_columns(
            (
                pl.col(f"{prefix}_gross_return") - pl.col(f"{prefix}_transaction_cost")
            ).alias(
                f"{prefix}_net_return",
            ),
        )
        .drop("_day", "_dcg", "_idcg", "_overlap")
    )


def holding_details(candidates: pl.DataFrame) -> pl.DataFrame:
    """Summarize selected holdings for each trading date."""
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
        pl.struct(
            "rank", "ts_code", "name", "prediction", "daily_return", "weight"
        ).alias("top30_holdings"),
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


def summarize(
    daily: pl.DataFrame,
    benchmark_keys: tuple[str, ...],
    annual_risk_free_rate: float,
    annualization_days: int,
) -> pl.DataFrame:
    """Combine overall, yearly, quarterly, and monthly backtest summaries."""
    frames = [
        _summarize_period(
            daily,
            period_type,
            benchmark_keys,
            annual_risk_free_rate,
            annualization_days,
        )
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
            ),
        )
        derived.extend(
            (
                pl.col(f"{prefix}_gross_return") - pl.col(f"benchmark_{key}_return")
            ).alias(
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
            ),
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


def validate_prediction_frame(
    frame: pl.DataFrame, index_columns: tuple[str, ...]
) -> None:
    """Validate dates, returns, and benchmark weights before backtesting."""
    if frame.is_empty():
        raise ValueError("预测文件为空")
    if frame.select("trade_date", "ts_code").n_unique() != frame.height:
        raise ValueError("预测文件包含重复的 trade_date, ts_code")
    invalid_number = pl.any_horizontal(
        pl.col("pred", "actual_return").is_not_null()
        & ~pl.col("pred", "actual_return").is_finite(),
    )
    invalid_label = pl.col("label_valid") & (
        pl.col("actual_return").is_null() | (pl.col("actual_return") <= -1)
    )
    if frame.filter(
        pl.col("trade_date").str.to_date("%Y%m%d", strict=False).is_null()
    ).height:
        raise ValueError("trade_date 必须是有效 YYYYMMDD")
    if frame.filter(invalid_number).height:
        raise ValueError("pred 或 actual_return 包含非有限值")
    if frame.filter(invalid_label).height:
        raise ValueError("有效 actual_return 必须非空且大于 -1")
    for column in index_columns:
        weight = pl.col(column)
        if frame.filter(
            weight.is_not_null() & (~weight.is_finite() | (weight < 0))
        ).height:
            raise ValueError(f"{column} 必须是非负有限小数权重")
        if frame.group_by("trade_date").agg(weight.sum()).filter(weight > 1.05).height:
            raise ValueError(f"{column} 每日合计不能明显超过 1")


class BacktestOutputParams(BaseOutputParams):
    daily_file: str
    summary_file: str
    dimensions: dict
    protocol: dict
    date_range: dict[str, str]
    days: int


class BacktestInputParams(BaseInputParams):
    transaction_cost_rate: float = Field(
        default=0.002,
        ge=0.0,
        lt=1.0,
        description="Transaction cost as a decimal rate applied to daily portfolio turnover.",
    )
    annual_risk_free_rate: float = Field(
        default=0.012,
        gt=-1.0,
        lt=1.0,
        description="Annual risk-free rate used to calculate risk-adjusted returns.",
    )
    annualization_days: int = Field(
        default=252,
        gt=0,
        description="Number of trading days used to annualize return and risk metrics.",
    )
    minimum_index_weight_coverage: float = Field(
        default=0.90,
        gt=0.0,
        le=1.0,
        description="Minimum daily index weight coverage required for benchmark returns.",
    )
    index_filter: str = Field(
        default="",
        description="Optional comma-separated index codes, such as hs300,zz500. Leave blank to include all buyable stocks.",
    )


@R.register("backtest")
class BacktestTask(BaseTask):
    """Evaluate one prediction task with daily top-N portfolios.

    Produces daily performance and period summaries with returns, turnover,
    ranking metrics, and available benchmark comparisons.
    """

    task_type = TaskType.BACKTEST

    REQUIRED_COLUMNS = (
        "trade_date",
        "ts_code",
        "name",
        "pred",
        "actual_return",
        "label_valid",
        "is_buyable",
    )
    input_cls = BacktestInputParams
    output_cls = BacktestOutputParams
    input_params: BacktestInputParams

    def build_task_steps(self) -> Iterable[TaskStep]:
        yield self.resolve_prediction_task
        yield self.load_and_validate_predictions
        yield self.calculate_daily_performance
        yield self.build_period_summaries
        yield self.write_outputs

    def resolve_prediction_task(self) -> None:
        prediction_task_id = self.input_params.source_task(TaskType.PREDICT)
        source_dir = self.source_task_dir(prediction_task_id)
        metadata_path = source_dir / "metadata.json"
        metadata = read_metadata(metadata_path)
        if (
            metadata.get("output_params", {})
            .get("protocol", {})
            .get("actual_return_unit")
            != "decimal"
        ):
            raise ValueError("Backtest requires decimal actual returns")
        output_dir = self.task_dir
        self.context.update(
            prediction_metadata_path=metadata_path,
            predictions_path=artifact_path(
                source_dir, metadata, "predictions"
            ),
            daily_path=output_dir / "daily.parquet",
            summary_path=output_dir / "summary.parquet",
        )

    def load_and_validate_predictions(self) -> None:
        path: Path = self.context["predictions_path"]
        if not path.is_file():
            raise FileNotFoundError(f"预测文件不存在: {path}")
        schema = pl.read_parquet_schema(path)
        self.report_progress(10)
        if missing := [name for name in self.REQUIRED_COLUMNS if name not in schema]:
            raise ValueError(f"预测文件缺少字段: {', '.join(missing)}")
        for name in ("label_valid", "is_buyable"):
            if schema[name] != pl.Boolean:
                raise TypeError(f"{name} 必须是 Boolean")
        index_columns = tuple(
            name for name in schema if name.startswith("index_weight_")
        )
        requested_indices = tuple(
            dict.fromkeys(
                part.strip().lower()
                for part in self.input_params.index_filter.replace("，", ",").split(",")
                if part.strip()
            )
        )
        available_indices = {
            name.removeprefix("index_weight_").lower(): name for name in index_columns
        }
        unknown_indices = [
            name for name in requested_indices if name not in available_indices
        ]
        if unknown_indices:
            available = ", ".join(sorted(available_indices)) or "无"
            raise ValueError(
                f"预测文件没有指数权重列: {', '.join(unknown_indices)}；可选指数: {available}"
            )
        frame = (
            pl.scan_parquet(path)
            .select(
                pl.col("trade_date", "ts_code", "name").cast(pl.String),
                pl.col("pred", "actual_return", *index_columns).cast(
                    pl.Float64, strict=False
                ),
                "label_valid",
                "is_buyable",
            )
            .collect()
            .sort("trade_date", "ts_code")
        )
        self.report_progress(55)
        self._validate_frame(frame, index_columns)
        candidate_filter = (
            pl.col("is_buyable") & pl.col("label_valid") & pl.col("pred").is_not_null()
        )
        if requested_indices:
            candidate_filter = candidate_filter & pl.any_horizontal(
                *(pl.col(available_indices[name]) > 0 for name in requested_indices)
            )
        candidates = enrich_candidates(frame.filter(candidate_filter))
        if candidates.is_empty():
            raise ValueError("预测文件没有可回测的可买样本")
        self.context.update(
            frame=frame,
            candidates=candidates,
            index_columns=index_columns,
            requested_indices=requested_indices,
        )
        self.report_progress(95)

    @staticmethod
    def _validate_frame(frame: pl.DataFrame, index_columns: tuple[str, ...]) -> None:
        """Preserve the Task helper while delegating prediction validation."""
        validate_prediction_frame(frame, index_columns)

    def calculate_daily_performance(self) -> None:
        candidates: pl.DataFrame = self.context["candidates"]
        frame: pl.DataFrame = self.context["frame"]
        daily = candidates.group_by("trade_date").agg(
            pl.len().alias("candidate_count"),
            correlation("pearson", "ic"),
            correlation("spearman", "rank_ic"),
        )
        universe = (
            frame.filter(pl.col("label_valid") & pl.col("actual_return").is_not_null())
            .group_by("trade_date")
            .agg(pl.col("actual_return").mean().alias("benchmark_universe_return"))
        )
        daily = daily.join(universe, on="trade_date", how="left")
        self.report_progress(20)
        indices = index_benchmarks(
            frame,
            self.context["index_columns"],
            self.input_params.minimum_index_weight_coverage,
        )
        if indices is not None:
            daily = daily.join(indices, on="trade_date", how="left")
        self.report_progress(35)
        portfolios = pl.collect_all(
            [
                portfolio_daily(
                    candidates, top_n, self.input_params.transaction_cost_rate
                ).lazy()
                for top_n in TOP_NS
            ],
        )
        for portfolio in portfolios:
            daily = daily.join(portfolio, on="trade_date", how="left")
        daily = daily.join(
            holding_details(candidates), on="trade_date", how="left"
        ).sort("trade_date")
        net_columns = [f"top{top_n}_net_return" for top_n in TOP_NS]
        if daily.filter(pl.any_horizontal(pl.col(*net_columns) <= -1)).height:
            raise ValueError("扣费后收益不能低于 -100%")
        self.context["daily"] = daily
        self.report_progress(95)

    def build_period_summaries(self) -> None:
        benchmark_keys = ("universe",) + tuple(
            column.removeprefix("index_weight_")
            for column in self.context["index_columns"]
        )
        self.context["benchmark_keys"] = benchmark_keys
        self.context["summary"] = summarize(
            self.context["daily"],
            benchmark_keys,
            self.input_params.annual_risk_free_rate,
            self.input_params.annualization_days,
        )
        self.report_progress(95)

    def write_outputs(self) -> None:
        for index, name in enumerate(("daily", "summary"), start=1):
            atomic_write(
                self.context[f"{name}_path"],
                lambda temporary, key=name: self.context[key].write_parquet(
                    temporary, compression="zstd"
                ),
            )
            self.report_progress(index / 2 * 95)

    def build_output_params(self) -> BacktestOutputParams:
        daily: pl.DataFrame = self.context["daily"]
        integrity = {
            name: artifact_record(
                self.context[f"{name}_path"], self.task_dir
            )
            for name in ("daily", "summary")
        }
        return self.output_cls(
            dimensions={
                "top_ns": list(TOP_NS),
                "holding_detail_top_n": HOLDING_DETAIL_TOP_N,
                "index_filter": list(self.context["requested_indices"]),
                "benchmarks": [
                    {
                        "key": key,
                        "label": "全市场平均" if key == "universe" else key.upper(),
                    }
                    for key in self.context["benchmark_keys"]
                ],
            },
            protocol={
                "actual_return": "decimal realized return supplied by the prediction task",
                "candidate_filter": "is_buyable and finite prediction and valid actual_return; optional index_weight_* > 0 (any selected index)",
                "portfolio": "daily equal-weight top-N ranked by descending prediction",
                "initial_turnover": 0.0,
                "turnover": "half L1 distance between consecutive target portfolios",
                "net_return": "gross return minus turnover times transaction_cost_rate",
                "ic": "daily Pearson correlation in the candidate universe",
                "rank_ic": "daily Spearman correlation in the candidate universe",
                "ndcg": "actual-return cross-sectional percentile relevance in the candidate universe",
                "icir": "annualized mean divided by sample standard deviation",
            },
            date_range={
                "start": daily["trade_date"].min(),
                "end": daily["trade_date"].max(),
            },
            days=daily.height,
            artifacts=integrity,
            daily_file=str(self.context["daily_path"]),
            summary_file=str(self.context["summary_path"]),
        )
