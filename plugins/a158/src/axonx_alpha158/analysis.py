"""Analyze every Alpha158 factor against all five realized-return horizons."""

from __future__ import annotations
import math
from collections.abc import Iterable
from pathlib import Path

import polars as pl
from pydantic import Field

from axonx.enums import TaskType
from axonx.task.contracts import (
    BaseAnalysisInputParams,
    BaseAnalysisOutputParams,
    BaseAnalysisTask,
)
from axonx.task.core import TaskStep
from axonx.task.storage import artifact_path, artifact_record, read_metadata
from axonx.utils.fs import atomic_write

from .internal.analysis import FactorMetricsCalculator
from .internal.etl_pipeline import LABELS


class FactorAnalysisOutputParams(BaseAnalysisOutputParams):
    quantiles_file: str
    feature_count: int
    labels: list[str]
    definitions: dict[str, str]


class FactorAnalysisInputParams(BaseAnalysisInputParams):
    """Configure factor diagnostics sourced from one Alpha158 ETL task."""

    quantiles: int = Field(default=10, ge=3, le=50, description="Number of factor-value groups used to compare subsequent returns.")
    minimum_daily_samples: int = Field(default=20, ge=2, description="Minimum valid stocks per day for a factor and return horizon.")
    feature_batch_size: int = Field(default=8, ge=1, le=32, description="Number of factors processed together in each batch.")
    tradable_only: bool = Field(default=True, description="Analyze only stocks marked buyable in the source dataset.")


class FactorAnalysisTask(BaseAnalysisTask):
    """Evaluate Alpha158 factors against five future return horizons.

    Reports correlation, stability, and quantile-based measures for each factor.
    """

    input_cls = FactorAnalysisInputParams
    output_cls = FactorAnalysisOutputParams
    input_params: FactorAnalysisInputParams

    def build_task_steps(self) -> Iterable[TaskStep]:
        yield self.resolve_upstream_task
        yield self.load_and_validate_dataset
        yield self.calculate_factor_metrics
        yield self.rank_factors
        yield self.write_outputs

    def resolve_upstream_task(self) -> None:
        etl_task_id = self.input_params.source_task(TaskType.ETL)
        source_dir = self.source_task_dir(etl_task_id)
        source_metadata_path = source_dir / "metadata.json"
        source_metadata = read_metadata(source_metadata_path)
        dataset_path = artifact_path(source_dir, source_metadata, "dataset")
        output_dir = self.task_dir
        self.state.update(
            source_dir=source_dir,
            source_metadata_path=source_metadata_path,
            source_metadata=source_metadata,
            dataset_path=dataset_path,
            result_path=output_dir / "factor_analysis.csv",
            quantiles_path=output_dir / "factor_quantiles.csv",
        )
        self.logger.info(
            f"Factor analysis source resolved etl_task_id={etl_task_id} "
            f"dataset={dataset_path} output_dir={output_dir}",
        )

    def load_and_validate_dataset(self) -> None:
        dataset_path: Path = self.state["dataset_path"]
        if not dataset_path.is_file():
            raise FileNotFoundError(f"Alpha158 数据不存在: {dataset_path}")
        metadata = self.state["source_metadata"]
        features = tuple(metadata.get("output_params", {}).get("feature_columns", ()))
        if not features:
            raise ValueError("ETL metadata 缺少 feature_columns")
        schema = pl.read_parquet_schema(dataset_path)
        self.report_progress(15)
        required = ("trade_date", "ts_code", *features, *LABELS)
        if self.input_params.tradable_only:
            required = (*required, "is_buyable")
        if missing := [column for column in required if column not in schema]:
            raise ValueError(f"Alpha158 数据缺少字段: {', '.join(missing[:20])}")
        stats = (
            pl.scan_parquet(dataset_path)
            .select(
                pl.len().alias("rows"),
                pl.col("trade_date").min().alias("start"),
                pl.col("trade_date").max().alias("end"),
            )
            .collect()
            .row(0, named=True)
        )
        self.report_progress(90)
        if not stats["rows"]:
            raise ValueError("Alpha158 数据为空")
        self.state.update(features=features, input_stats=stats)
        self.report_progress(95)
        self.logger.info(
            f"Factor analysis data validated rows={stats['rows']} features={len(features)} "
            f"start={stats['start']} end={stats['end']}",
        )

    def calculate_factor_metrics(self) -> None:
        results: list[pl.DataFrame] = []
        quantile_results: list[pl.DataFrame] = []
        features: tuple[str, ...] = self.state["features"]
        total = len(features)
        calculator = FactorMetricsCalculator(self.input_params.minimum_daily_samples, self.input_params.quantiles)
        for offset in range(0, total, self.input_params.feature_batch_size):
            batch = features[offset : offset + self.input_params.feature_batch_size]
            columns = ("trade_date", *batch, *LABELS)
            if self.input_params.tradable_only:
                columns = (*columns, "is_buyable")
            source = pl.scan_parquet(self.state["dataset_path"]).select(columns)
            if self.input_params.tradable_only:
                source = source.filter("is_buyable").drop("is_buyable")
            frame = source.collect()
            batch_results, batch_quantiles = calculator.analyze_batch(frame, batch)
            results.append(batch_results)
            quantile_results.append(batch_quantiles)
            completed = min(offset + len(batch), total)
            percentage = completed / total * 95
            self.report_progress(percentage)
            self.logger.info(f"Factor diagnostics progress completed={completed}/{total} last_factor={batch[-1]}")
        self.state["results"] = pl.concat(results, how="vertical")
        self.state["quantile_results"] = pl.concat(quantile_results, how="vertical").sort(
            "factor",
            "label",
            "quantile",
        )

    def rank_factors(self) -> None:
        results: pl.DataFrame = self.state["results"]
        self.state["results"] = results.with_columns(
            (pl.col("rankic_mean").abs().rank(method="average", descending=True).over("label")).alias(
                "rank_by_abs_rankic",
            ),
            (pl.col("rankicir").abs().rank(method="average", descending=True).over("label")).alias(
                "rank_by_abs_rankicir",
            ),
        ).sort("label", "rank_by_abs_rankic")

    def write_outputs(self) -> None:
        output_dir: Path = self.task_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        outputs = (
            ("results", "result_path"),
            ("quantile_results", "quantiles_path"),
        )
        for index, (key, path_key) in enumerate(outputs, start=1):
            path: Path = self.state[path_key]
            atomic_write(path, self.state[key].write_csv)
            self.report_progress(index / len(outputs) * 95)
        self.logger.info(
            f"Factor analysis outputs written result={self.state['result_path']} "
            f"quantiles={self.state['quantiles_path']} rows={self.state['results'].height}",
        )

    def build_output_params(self) -> FactorAnalysisOutputParams:
        output_dir: Path = self.task_dir
        result_record = artifact_record(self.state["result_path"], output_dir)
        quantiles_record = artifact_record(self.state["quantiles_path"], output_dir)
        scores: dict[str, dict[str, float]] = {}
        for row in self.state["results"].iter_rows(named=True):
            for metric in ("ic_mean", "rankic_mean"):
                value = row[metric]
                if value is not None and math.isfinite(value):
                    scores.setdefault(f"{metric}/{row['label']}", {})[row["factor"]] = float(value)
        return self.output_cls(
            feature_count=len(self.state["features"]),
            labels=list(LABELS),
            rows=self.state["results"].height,
            scores=scores,
            definitions={
                "icir": "mean daily cross-sectional Pearson IC divided by its sample standard deviation",
                "rankicir": "mean daily cross-sectional Spearman RankIC divided by its sample standard deviation",
                "quantile_spread": "highest quantile mean raw return minus lowest quantile mean raw return",
                "quantile_monotonicity": "Spearman correlation between quantile order and mean raw return",
                "sample_filter": "is_buyable" if self.input_params.tradable_only else "none",
            },
            artifacts={
                "result": result_record,
                "quantiles": quantiles_record,
            },
            result_file=str(self.state["result_path"]),
            quantiles_file=str(self.state["quantiles_path"]),
        )
