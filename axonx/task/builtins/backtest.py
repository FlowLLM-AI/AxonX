"""Task orchestration for built-in prediction backtests."""

from collections.abc import Iterable
from pathlib import Path

import polars as pl

from ...components.registry import provider
from ...enums import TaskType
from ...utils.fs import atomic_write
from ..core import BaseTask, TaskStep
from ..storage.artifacts import artifact_path, artifact_record, read_metadata
from ..storage.workspace import METADATA_FILE
from .backtest_metrics import summarize
from .backtest_models import BacktestInputParams, BacktestOutputParams
from .backtest_portfolio import (
    HOLDING_DETAIL_TOP_N,
    TOP_NS,
    correlation,
    enrich_candidates,
    holding_details,
    index_benchmarks,
    portfolio_daily,
)
from .backtest_validation import validate_prediction_frame


@provider("backtest")
class BacktestTask(BaseTask):
    """Evaluate one prediction task with daily top-N portfolios."""

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
        metadata_path = source_dir / METADATA_FILE
        metadata = read_metadata(metadata_path)
        if (
            metadata.get("output_params", {})
            .get("protocol", {})
            .get("actual_return_unit")
            != "decimal"
        ):
            raise ValueError("Backtest requires decimal actual returns")
        output_dir = self.task_dir
        self.state.update(
            prediction_metadata_path=metadata_path,
            predictions_path=artifact_path(source_dir, metadata, "predictions"),
            daily_path=output_dir / "daily.parquet",
            summary_path=output_dir / "summary.parquet",
        )

    def load_and_validate_predictions(self) -> None:
        path: Path = self.state["predictions_path"]
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
            candidate_filter &= pl.any_horizontal(
                *(pl.col(available_indices[name]) > 0 for name in requested_indices)
            )
        candidates = enrich_candidates(frame.filter(candidate_filter))
        if candidates.is_empty():
            raise ValueError("预测文件没有可回测的可买样本")
        self.state.update(
            frame=frame,
            candidates=candidates,
            index_columns=index_columns,
            requested_indices=requested_indices,
        )
        self.report_progress(95)

    @staticmethod
    def _validate_frame(frame: pl.DataFrame, index_columns: tuple[str, ...]) -> None:
        validate_prediction_frame(frame, index_columns)

    def calculate_daily_performance(self) -> None:
        candidates: pl.DataFrame = self.state["candidates"]
        frame: pl.DataFrame = self.state["frame"]
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
            self.state["index_columns"],
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
            ]
        )
        for portfolio in portfolios:
            daily = daily.join(portfolio, on="trade_date", how="left")
        daily = daily.join(
            holding_details(candidates), on="trade_date", how="left"
        ).sort("trade_date")
        net_columns = [f"top{top_n}_net_return" for top_n in TOP_NS]
        if daily.filter(pl.any_horizontal(pl.col(*net_columns) <= -1)).height:
            raise ValueError("扣费后收益不能低于 -100%")
        self.state["daily"] = daily
        self.report_progress(95)

    def build_period_summaries(self) -> None:
        benchmark_keys = ("universe",) + tuple(
            column.removeprefix("index_weight_")
            for column in self.state["index_columns"]
        )
        self.state["benchmark_keys"] = benchmark_keys
        self.state["summary"] = summarize(
            self.state["daily"],
            benchmark_keys,
            self.input_params.annual_risk_free_rate,
            self.input_params.annualization_days,
        )
        self.report_progress(95)

    def write_outputs(self) -> None:
        for index, name in enumerate(("daily", "summary"), start=1):
            atomic_write(
                self.state[f"{name}_path"],
                lambda temporary, key=name: self.state[key].write_parquet(
                    temporary, compression="zstd"
                ),
            )
            self.report_progress(index / 2 * 95)

    def build_output_params(self) -> BacktestOutputParams:
        daily: pl.DataFrame = self.state["daily"]
        integrity = {
            name: artifact_record(self.state[f"{name}_path"], self.task_dir)
            for name in ("daily", "summary")
        }
        return self.output_cls(
            dimensions={
                "top_ns": list(TOP_NS),
                "holding_detail_top_n": HOLDING_DETAIL_TOP_N,
                "index_filter": list(self.state["requested_indices"]),
                "benchmarks": [
                    {
                        "key": key,
                        "label": "全市场平均" if key == "universe" else key.upper(),
                    }
                    for key in self.state["benchmark_keys"]
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
            daily_file=str(self.state["daily_path"]),
            summary_file=str(self.state["summary_path"]),
        )
