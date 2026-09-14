"""Vectorized Polars backtest for Alpha158 predictions."""

from __future__ import annotations

import math
from collections.abc import Iterable
from pathlib import Path

import polars as pl
from pydantic import Field, field_validator

from ...components.registry import R
from ...enums import TaskType
from ..base import BaseConfig, BaseTask, TaskStep
from ._artifacts import (
    artifact_path,
    artifact_record,
    atomic_output,
    metadata_header,
    read_metadata,
    task_directory,
    write_metadata,
)


class Alpha158BacktestConfig(BaseConfig):
    prediction_task_id: str
    top_ns: str = "1,2,3,4,5,10,20,30,50"
    holdings_top_n: int = Field(default=50, gt=0, le=500)
    transaction_cost_rate: float = Field(default=0.002, ge=0.0, lt=1.0)
    annual_risk_free_rate: float = Field(default=0.012, gt=-1.0, lt=1.0)
    annualization_days: int = Field(default=252, gt=0)
    minimum_index_weight_coverage: float = Field(default=0.90, gt=0.0, le=1.0)

    @field_validator("top_ns")
    @classmethod
    def validate_top_ns(cls, value: str) -> str:
        values = cls.parse_top_ns(value)
        if len(values) != len(set(values)):
            raise ValueError("top_ns 不能重复")
        return ",".join(map(str, values))

    @staticmethod
    def parse_top_ns(value: str) -> tuple[int, ...]:
        try:
            result = tuple(int(part) for part in value.split(",") if part.strip())
        except ValueError as exc:
            raise ValueError("top_ns 必须是逗号分隔的正整数") from exc
        if not result or min(result) <= 0:
            raise ValueError("top_ns 必须是逗号分隔的正整数")
        return result


@R.register("alpha158_backtest")
class Alpha158BacktestTask(BaseTask):
    """Build daily portfolios and period diagnostics with Polars expressions."""

    REQUIRED_COLUMNS = (
        "trade_date",
        "ts_code",
        "name",
        "pred",
        "actual_return",
        "label_valid",
        "is_buyable",
    )
    config_cls = Alpha158BacktestConfig
    config: Alpha158BacktestConfig
    task_type = TaskType.BACKTEST
    output_keys = (
        "daily_file",
        "holdings_file",
        "overall_file",
        "yearly_file",
        "quarterly_file",
        "metadata_file",
        "days",
    )

    def build_task_steps(self) -> Iterable[TaskStep]:
        yield self.resolve_prediction_task
        yield self.load_and_validate_predictions
        yield self.calculate_daily_performance
        yield self.build_period_summaries
        yield self.write_outputs
        yield self.write_metadata
        yield self.publish_output

    def resolve_prediction_task(self) -> None:
        source_dir = task_directory(self.workspace_path, "predict", self.config.prediction_task_id)
        metadata_path = source_dir / "metadata.json"
        metadata = read_metadata(metadata_path, description="Alpha158 prediction")
        if metadata.get("protocol", {}).get("actual_return_column") != "label_1d":
            raise ValueError("回测只接受以原始 label_1d 为 actual_return 的预测任务")
        output_dir = self.workspace_path / "backtest" / self.task_id
        names = ("daily", "holdings", "overall", "yearly", "quarterly")
        self.context.update(
            prediction_metadata_path=metadata_path,
            predictions_path=artifact_path(source_dir, metadata, "predictions"),
            output_dir=output_dir,
            metadata_path=output_dir / "metadata.json",
            top_ns=Alpha158BacktestConfig.parse_top_ns(self.config.top_ns),
            **{f"{name}_path": output_dir / f"{name}.csv" for name in names},
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
        index_columns = tuple(name for name in schema if name.startswith("index_weight_"))
        frame = (
            pl.scan_parquet(path)
            .select(
                pl.col("trade_date", "ts_code", "name").cast(pl.String),
                pl.col("pred", "actual_return", *index_columns).cast(pl.Float64, strict=False),
                "label_valid",
                "is_buyable",
            )
            .collect()
            .sort("trade_date", "ts_code")
        )
        self.report_progress(55)
        if frame.is_empty():
            raise ValueError("预测文件为空")
        if frame.select("trade_date", "ts_code").n_unique() != frame.height:
            raise ValueError("预测文件包含重复的 trade_date, ts_code")
        invalid_number = pl.any_horizontal(
            pl.col("pred", "actual_return").is_not_null() & ~pl.col("pred", "actual_return").is_finite(),
        )
        invalid_label = pl.col("label_valid") & (pl.col("actual_return").is_null() | (pl.col("actual_return") <= -1))
        if frame.filter(pl.col("trade_date").str.to_date("%Y%m%d", strict=False).is_null()).height:
            raise ValueError("trade_date 必须是有效 YYYYMMDD")
        if frame.filter(invalid_number).height:
            raise ValueError("pred 或 actual_return 包含非有限值")
        if frame.filter(invalid_label).height:
            raise ValueError("有效 actual_return 必须非空且大于 -1")
        for column in index_columns:
            weight = pl.col(column)
            if frame.filter(weight.is_not_null() & (~weight.is_finite() | (weight < 0))).height:
                raise ValueError(f"{column} 必须是非负有限小数权重")
            if frame.group_by("trade_date").agg(weight.sum()).filter(weight > 1.05).height:
                raise ValueError(f"{column} 每日合计不能明显超过 1")
        eligible = pl.col("is_buyable") & pl.col("label_valid") & pl.col("pred").is_not_null()
        candidates = (
            frame.filter(eligible)
            .sort("trade_date", "pred", "ts_code", descending=(False, True, False))
            .with_columns(pl.col("ts_code").cum_count().over("trade_date").alias("rank"))
        )
        if candidates.is_empty():
            raise ValueError("预测文件没有可回测的 label_1d 样本")
        self.context.update(frame=frame, candidates=candidates, index_columns=index_columns)
        self.report_progress(95)

    def calculate_daily_performance(self) -> None:
        candidates: pl.DataFrame = self.context["candidates"]
        base = candidates.group_by("trade_date").agg(
            pl.len().alias("candidates"),
            self._correlation("pearson", "ic"),
            self._correlation("spearman", "rank_ic"),
            pl.col("actual_return").mean().alias("benchmark_universe"),
        )
        self.report_progress(15)
        benchmarks = self._index_benchmarks(self.context["frame"])
        if benchmarks is not None:
            base = base.join(benchmarks, on="trade_date", how="left")
        self.report_progress(30)
        daily = base
        portfolios = pl.collect_all([self._portfolio(candidates, n).lazy() for n in self.context["top_ns"]])
        self.report_progress(65)
        for portfolio in portfolios:
            daily = daily.join(portfolio, on="trade_date", how="left")
        daily = daily.sort("trade_date")
        net_columns = [f"top{n}_net_return" for n in self.context["top_ns"]]
        if daily.filter(pl.any_horizontal(pl.col(*net_columns) <= -1)).height:
            raise ValueError("扣费后收益不能低于 -100%")
        daily = daily.with_columns(
            (pl.col(name) + 1).cum_prod().alias(name.replace("return", "value")) for name in net_columns
        )
        self.report_progress(85)
        holdings = (
            candidates.filter(pl.col("rank") <= self.config.holdings_top_n)
            .with_columns(
                (1 / pl.len().over("trade_date")).alias("weight"),
                pl.col("pred").alias("prediction"),
                pl.col("actual_return").alias("daily_return"),
            )
            .select(
                "trade_date",
                "rank",
                "ts_code",
                "name",
                "prediction",
                "weight",
                "daily_return",
            )
        )
        self.context.update(daily=daily, holdings=holdings)
        self.report_progress(95)

    @staticmethod
    def _correlation(method: str, name: str) -> pl.Expr:
        return pl.corr("pred", "actual_return", method=method).fill_nan(0).fill_null(0).alias(name)

    def _index_benchmarks(self, frame: pl.DataFrame) -> pl.DataFrame | None:
        expressions = []
        for column in self.context["index_columns"]:
            suffix = column.removeprefix("index_weight_")
            valid = pl.col("label_valid") & pl.col("actual_return").is_not_null() & pl.col(column).is_not_null()
            covered = pl.col(column).filter(valid).sum()
            expressions.extend(
                (
                    covered.clip(upper_bound=1).alias(f"benchmark_{suffix}_coverage"),
                    pl.when(covered >= self.config.minimum_index_weight_coverage)
                    .then((pl.col(column) * pl.col("actual_return")).filter(valid).sum() / covered)
                    .alias(f"benchmark_{suffix}"),
                ),
            )
        return frame.group_by("trade_date").agg(*expressions) if expressions else None

    def _portfolio(self, candidates: pl.DataFrame, top_n: int) -> pl.DataFrame:
        prefix = f"top{top_n}"
        selected = candidates.filter(pl.col("rank") <= top_n).with_columns(
            (1 / pl.len().over("trade_date")).alias("weight"),
        )
        dates = selected.select("trade_date").unique().sort("trade_date").with_row_index("_day")
        weights = selected.join(dates, on="trade_date").select(
            "_day",
            "trade_date",
            "ts_code",
            "weight",
            "actual_return",
        )
        previous = weights.select(
            (pl.col("_day") + 1).alias("_day"),
            "ts_code",
            pl.col("weight").alias("_previous_weight"),
        )
        return (
            weights.join(previous, on=("_day", "ts_code"), how="left")
            .group_by("_day", "trade_date")
            .agg(
                pl.len().alias(f"{prefix}_count"),
                pl.col("actual_return").mean().alias(f"{prefix}_gross_return"),
                pl.when(pl.col("_previous_weight").is_not_null())
                .then(pl.min_horizontal("weight", "_previous_weight"))
                .otherwise(0)
                .sum()
                .alias("_overlap"),
            )
            .sort("_day")
            .with_columns(
                pl.when(pl.col("_day") == 0)
                .then(0)
                .otherwise(1 - pl.col("_overlap").fill_null(0))
                .alias(f"{prefix}_turnover"),
            )
            .with_columns(
                (pl.col(f"{prefix}_turnover") * self.config.transaction_cost_rate).alias(f"{prefix}_transaction_cost"),
            )
            .with_columns(
                (pl.col(f"{prefix}_gross_return") - pl.col(f"{prefix}_transaction_cost")).alias(f"{prefix}_net_return"),
            )
            .drop("_day", "_overlap")
        )

    def build_period_summaries(self) -> None:
        daily: pl.DataFrame = self.context["daily"]
        dated = daily.with_columns(
            pl.col("trade_date").str.slice(0, 4).alias("year"),
            (
                pl.col("trade_date").str.slice(0, 4)
                + "Q"
                + (((pl.col("trade_date").str.slice(4, 2).cast(pl.Int8) - 1) // 3) + 1).cast(pl.String)
            ).alias("quarter"),
        )
        self.context["overall"] = self._summarize(daily.with_columns(pl.lit("overall").alias("period")), "period")
        self.report_progress(30)
        self.context["yearly"] = self._summarize(dated, "year")
        self.report_progress(60)
        self.context["quarterly"] = self._summarize(dated, "quarter")
        self.report_progress(95)

    @staticmethod
    def _ratio(column: str) -> pl.Expr:
        values = pl.col(column).drop_nulls()
        std = values.std(ddof=1)
        return pl.when((values.len() > 1) & (std > 0)).then(values.mean() / std).otherwise(0)

    def _summarize(self, frame: pl.DataFrame, period: str) -> pl.DataFrame:
        frame = frame.rename({period: "_period"})
        daily_rf = (1 + self.config.annual_risk_free_rate) ** (1 / self.config.annualization_days) - 1
        derived = []
        for n in self.context["top_ns"]:
            net = f"top{n}_net_return"
            derived.extend(
                (
                    (pl.col(net) + 1).cum_prod().over("_period").alias(f"_{n}_equity"),
                    (pl.col(net) - daily_rf).alias(f"_{n}_excess"),
                ),
            )
        frame = frame.sort("_period", "trade_date").with_columns(*derived)
        metrics = [
            pl.len().alias("all|none|trading_days"),
            pl.col("ic").mean().alias("all|none|ic_mean"),
            self._ratio("ic").alias("all|none|icir"),
            pl.col("rank_ic").mean().alias("all|none|rankic_mean"),
            self._ratio("rank_ic").alias("all|none|rankicir"),
        ]
        benchmarks = ("benchmark_universe",) + tuple(
            f"benchmark_{name.removeprefix('index_weight_')}" for name in self.context["index_columns"]
        )
        for n in self.context["top_ns"]:
            portfolio, net, equity = f"top{n}", f"top{n}_net_return", f"_{n}_equity"
            cumulative = (pl.col(net) + 1).product()
            metrics.extend(
                (
                    pl.col(f"{portfolio}_gross_return").sum().alias(f"{portfolio}|none|gross_cumulative_return"),
                    (cumulative - 1).alias(f"{portfolio}|none|net_cumulative_return"),
                    pl.when(cumulative > 0)
                    .then(cumulative.pow(self.config.annualization_days / pl.len()) - 1)
                    .otherwise(-1)
                    .alias(f"{portfolio}|none|annualized_net_return"),
                    (pl.col(net).std(ddof=1) * math.sqrt(self.config.annualization_days)).alias(
                        f"{portfolio}|none|annualized_volatility",
                    ),
                    (self._ratio(f"_{n}_excess") * math.sqrt(self.config.annualization_days)).alias(
                        f"{portfolio}|none|sharpe",
                    ),
                    (pl.col(equity) / pl.col(equity).cum_max() - 1).min().alias(f"{portfolio}|none|max_drawdown"),
                    (pl.col(net) > 0).mean().alias(f"{portfolio}|none|win_rate"),
                    pl.col(f"{portfolio}_turnover").mean().alias(f"{portfolio}|none|average_turnover"),
                    pl.col(f"{portfolio}_count").mean().alias(f"{portfolio}|none|average_holding_count"),
                ),
            )
            for benchmark in benchmarks:
                active = f"_{n}_{benchmark}_active"
                frame = frame.with_columns((pl.col(net) - pl.col(benchmark)).alias(active))
                metrics.extend(
                    (
                        pl.when(pl.col(active).is_not_null().any())
                        .then(pl.col(active).drop_nulls().sum())
                        .alias(f"{portfolio}|{benchmark}|active_cumulative_return"),
                        pl.when(pl.col(active).is_not_null().any())
                        .then(self._ratio(active) * math.sqrt(self.config.annualization_days))
                        .alias(f"{portfolio}|{benchmark}|information_ratio"),
                    ),
                )
        return (
            frame.group_by("_period", maintain_order=True)
            .agg(*metrics)
            .unpivot(index="_period", variable_name="_metric", value_name="value")
            .with_columns(pl.col("_metric").str.split_exact("|", 2).alias("_parts"))
            .select(
                pl.col("_period").alias("period"),
                pl.col("_parts").struct.field("field_0").alias("portfolio"),
                pl.col("_parts").struct.field("field_1").alias("benchmark"),
                pl.col("_parts").struct.field("field_2").alias("metric"),
                "value",
            )
            .filter(pl.col("value").is_finite())
        )

    def write_outputs(self) -> None:
        self.context["output_dir"].mkdir(parents=True, exist_ok=True)
        names = ("daily", "holdings", "overall", "yearly", "quarterly")
        for index, name in enumerate(names, start=1):
            atomic_output(self.context[f"{name}_path"], self.context[name].write_csv)
            self.report_progress(index / len(names) * 95)

    def write_metadata(self) -> None:
        names = ("daily", "holdings", "overall", "yearly", "quarterly")
        daily: pl.DataFrame = self.context["daily"]
        integrity = {}
        for index, name in enumerate(names, start=1):
            integrity[name] = artifact_record(self.context[f"{name}_path"], self.context["output_dir"])
            self.report_progress(index / (len(names) + 1) * 90)
        metadata = {
            **metadata_header(
                task_name="alpha158_backtest",
                task_id=self.task_id,
                task_type=self.task_type.value,
            ),
            "config": self.config.model_dump(mode="json", exclude={"task_id", "task_type"}),
            "source": {
                "prediction_task_id": self.config.prediction_task_id,
                "metadata": str(self.context["prediction_metadata_path"]),
            },
            "protocol": {
                "actual_return": "raw label_1d decimal adjusted-close return",
                "candidate_filter": "is_buyable and finite prediction and valid label_1d",
                "portfolio": "daily equal-weight top-N ranked by descending prediction",
                "initial_turnover": 0.0,
                "turnover": "half L1 distance between consecutive target portfolios",
                "net_return": "gross return minus turnover times transaction_cost_rate",
                "ic": "daily Pearson correlation between prediction and raw label_1d",
                "rank_ic": "daily Spearman correlation between prediction and raw label_1d",
            },
            "date_range": {
                "start": daily["trade_date"].min(),
                "end": daily["trade_date"].max(),
            },
            "days": daily.height,
            "index_weight_columns": list(self.context["index_columns"]),
            "artifacts": {name: f"{name}.csv" for name in names},
            "artifact_integrity": integrity,
        }
        write_metadata(self.context["metadata_path"], metadata)
        self.report_progress(95)

    def publish_output(self) -> None:
        names = ("daily", "holdings", "overall", "yearly", "quarterly")
        self.context.update(
            **{f"{name}_file": str(self.context[f"{name}_path"]) for name in names},
            metadata_file=str(self.context["metadata_path"]),
            days=self.context["daily"].height,
        )
