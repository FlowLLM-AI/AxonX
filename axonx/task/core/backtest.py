"""Generate daily and summary Parquet backtest artifacts."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import polars as pl
from pydantic import Field

from ...components.registry import R
from ...enums import TaskType
from ..base import BaseInputParams, BaseOutputParams, BaseTask, TaskStep
from .artifacts import (
    artifact_path,
    artifact_record,
    atomic_output,
    read_metadata,
    task_directory,
)
from .backtest_metrics import (
    HOLDING_DETAIL_TOP_N,
    TOP_NS,
    correlation,
    enrich_candidates,
    holding_details,
    index_benchmarks,
    portfolio_daily,
    summarize,
    validate_prediction_frame,
)


class BacktestOutputParams(BaseOutputParams):
    metadata_file: str
    daily_file: str
    summary_file: str
    dimensions: dict
    protocol: dict
    date_range: dict[str, str]
    days: int


class BacktestInputParams(BaseInputParams):
    prediction_task_id: str
    transaction_cost_rate: float = Field(default=0.002, ge=0.0, lt=1.0)
    annual_risk_free_rate: float = Field(default=0.012, gt=-1.0, lt=1.0)
    annualization_days: int = Field(default=252, gt=0)
    minimum_index_weight_coverage: float = Field(default=0.90, gt=0.0, le=1.0)


@R.register("backtest")
class BacktestTask(BaseTask):
    """Build the complete backtest report from one prediction artifact."""

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
        source_dir = task_directory(self.workspace_path, "predict", self.input_params.prediction_task_id)
        metadata_path = source_dir / "metadata.json"
        metadata = read_metadata(metadata_path, description="prediction")
        if metadata.get("output_params", {}).get("protocol", {}).get("actual_return_unit") != "decimal":
            raise ValueError("Backtest requires decimal actual returns")
        output_dir = self.workspace_path / "backtest" / self.task_id
        self.context.update(
            prediction_metadata_path=metadata_path,
            predictions_path=artifact_path(source_dir, metadata, "predictions"),
            output_dir=output_dir,
            daily_path=output_dir / "daily.parquet",
            summary_path=output_dir / "summary.parquet",
            metadata_path=output_dir / "metadata.json",
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
        self._validate_frame(frame, index_columns)
        candidates = enrich_candidates(
            frame.filter(pl.col("is_buyable") & pl.col("label_valid") & pl.col("pred").is_not_null()),
        )
        if candidates.is_empty():
            raise ValueError("预测文件没有可回测的可买样本")
        self.context.update(frame=frame, candidates=candidates, index_columns=index_columns)
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
            [portfolio_daily(candidates, top_n, self.input_params.transaction_cost_rate).lazy() for top_n in TOP_NS],
        )
        for portfolio in portfolios:
            daily = daily.join(portfolio, on="trade_date", how="left")
        daily = daily.join(holding_details(candidates), on="trade_date", how="left").sort("trade_date")
        net_columns = [f"top{top_n}_net_return" for top_n in TOP_NS]
        if daily.filter(pl.any_horizontal(pl.col(*net_columns) <= -1)).height:
            raise ValueError("扣费后收益不能低于 -100%")
        self.context["daily"] = daily
        self.report_progress(95)

    def build_period_summaries(self) -> None:
        benchmark_keys = ("universe",) + tuple(
            column.removeprefix("index_weight_") for column in self.context["index_columns"]
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
        self.context["output_dir"].mkdir(parents=True, exist_ok=True)
        for index, name in enumerate(("daily", "summary"), start=1):
            atomic_output(
                self.context[f"{name}_path"],
                lambda temporary, key=name: self.context[key].write_parquet(temporary, compression="zstd"),
            )
            self.report_progress(index / 2 * 95)

    def build_output_params(self) -> BacktestOutputParams:
        daily: pl.DataFrame = self.context["daily"]
        integrity = {
            name: artifact_record(self.context[f"{name}_path"], self.context["output_dir"])
            for name in ("daily", "summary")
        }
        return self.output_cls(
            dimensions={
                "top_ns": list(TOP_NS),
                "holding_detail_top_n": HOLDING_DETAIL_TOP_N,
                "benchmarks": [
                    {"key": key, "label": "全市场平均" if key == "universe" else key.upper()}
                    for key in self.context["benchmark_keys"]
                ],
            },
            protocol={
                "actual_return": "decimal realized return supplied by the prediction task",
                "candidate_filter": "is_buyable and finite prediction and valid actual_return",
                "portfolio": "daily equal-weight top-N ranked by descending prediction",
                "initial_turnover": 0.0,
                "turnover": "half L1 distance between consecutive target portfolios",
                "net_return": "gross return minus turnover times transaction_cost_rate",
                "ic": "daily Pearson correlation in the candidate universe",
                "rank_ic": "daily Spearman correlation in the candidate universe",
                "ndcg": "actual-return cross-sectional percentile relevance in the candidate universe",
                "icir": "annualized mean divided by sample standard deviation",
            },
            date_range={"start": daily["trade_date"].min(), "end": daily["trade_date"].max()},
            days=daily.height,
            artifacts=integrity,
            daily_file=str(self.context["daily_path"]),
            summary_file=str(self.context["summary_path"]),
            metadata_file=str(self.context["metadata_path"]),
        )
