"""Analyze every Alpha158 factor against all five realized-return horizons."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import polars as pl
from pydantic import Field

from ...components.registry import R
from ...enums import TaskType
from ..base import BaseConfig, BaseTask, TaskStep
from .internal.artifacts import (
    artifact_path,
    artifact_record,
    atomic_output,
    metadata_header,
    read_metadata,
    task_directory,
    write_metadata,
)
from .internal.etl_pipeline import LABELS
from .internal.analysis import FactorMetricsCalculator


class FactorAnalysisConfig(BaseConfig):
    """Configure factor diagnostics sourced from one Alpha158 ETL task."""

    etl_task_id: str
    quantiles: int = Field(default=10, ge=3, le=50)
    minimum_daily_samples: int = Field(default=20, ge=2)
    feature_batch_size: int = Field(default=8, ge=1, le=32)
    tradable_only: bool = True


@R.register("alpha158_factor_analysis")
class FactorAnalysisTask(BaseTask):
    """Measure IC, RankIC, stability, quantile spread, and monotonicity for 158 factors and five raw labels."""

    config_cls = FactorAnalysisConfig
    config: FactorAnalysisConfig
    task_type = TaskType.ANALYSIS
    output_keys = ("result_file", "quantiles_file", "metadata_file", "rows")

    def build_task_steps(self) -> Iterable[TaskStep]:
        yield self.resolve_upstream_task
        yield self.load_and_validate_dataset
        yield self.calculate_factor_metrics
        yield self.rank_factors
        yield self.write_outputs
        yield self.write_metadata
        yield self.publish_output

    def resolve_upstream_task(self) -> None:
        source_dir = task_directory(self.workspace_path, "etl", self.config.etl_task_id)
        source_metadata_path = source_dir / "metadata.json"
        source_metadata = read_metadata(source_metadata_path, description="Alpha158 ETL")
        dataset_path = artifact_path(source_dir, source_metadata, "dataset")
        output_dir = self.workspace_path / "analysis" / self.task_id
        self.context.update(
            source_dir=source_dir,
            source_metadata_path=source_metadata_path,
            source_metadata=source_metadata,
            dataset_path=dataset_path,
            output_dir=output_dir,
            result_path=output_dir / "factor_analysis.csv",
            quantiles_path=output_dir / "factor_quantiles.csv",
            metadata_path=output_dir / "metadata.json",
        )
        self.logger.info(
            f"Factor analysis source resolved etl_task_id={self.config.etl_task_id} "
            f"dataset={dataset_path} output_dir={output_dir}",
        )

    def load_and_validate_dataset(self) -> None:
        dataset_path: Path = self.context["dataset_path"]
        if not dataset_path.is_file():
            raise FileNotFoundError(f"Alpha158 数据不存在: {dataset_path}")
        metadata = self.context["source_metadata"]
        features = tuple(metadata.get("feature_columns", ()))
        if not features:
            raise ValueError("ETL metadata 缺少 feature_columns")
        schema = pl.read_parquet_schema(dataset_path)
        self.report_progress(15)
        required = ("trade_date", "ts_code", *features, *LABELS)
        if self.config.tradable_only:
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
        self.context.update(features=features, input_stats=stats)
        self.report_progress(95)
        self.logger.info(
            f"Factor analysis data validated rows={stats['rows']} features={len(features)} "
            f"start={stats['start']} end={stats['end']}",
        )

    def calculate_factor_metrics(self) -> None:
        results: list[pl.DataFrame] = []
        quantile_results: list[pl.DataFrame] = []
        features: tuple[str, ...] = self.context["features"]
        total = len(features)
        calculator = FactorMetricsCalculator(self.config.minimum_daily_samples, self.config.quantiles)
        for offset in range(0, total, self.config.feature_batch_size):
            batch = features[offset : offset + self.config.feature_batch_size]
            columns = ("trade_date", *batch, *LABELS)
            if self.config.tradable_only:
                columns = (*columns, "is_buyable")
            source = pl.scan_parquet(self.context["dataset_path"]).select(columns)
            if self.config.tradable_only:
                source = source.filter("is_buyable").drop("is_buyable")
            frame = source.collect()
            batch_results, batch_quantiles = calculator.analyze_batch(frame, batch)
            results.append(batch_results)
            quantile_results.append(batch_quantiles)
            completed = min(offset + len(batch), total)
            percentage = completed / total * 95
            self.report_progress(percentage)
            self.logger.info(f"Factor diagnostics progress completed={completed}/{total} last_factor={batch[-1]}")
        self.context["results"] = pl.concat(results, how="vertical")
        self.context["quantile_results"] = pl.concat(quantile_results, how="vertical").sort(
            "factor",
            "label",
            "quantile",
        )

    def rank_factors(self) -> None:
        results: pl.DataFrame = self.context["results"]
        self.context["results"] = results.with_columns(
            (pl.col("rankic_mean").abs().rank(method="average", descending=True).over("label")).alias(
                "rank_by_abs_rankic",
            ),
            (pl.col("rankicir").abs().rank(method="average", descending=True).over("label")).alias(
                "rank_by_abs_rankicir",
            ),
        ).sort("label", "rank_by_abs_rankic")

    def write_outputs(self) -> None:
        output_dir: Path = self.context["output_dir"]
        output_dir.mkdir(parents=True, exist_ok=True)
        outputs = (
            ("results", "result_path"),
            ("quantile_results", "quantiles_path"),
        )
        for index, (key, path_key) in enumerate(outputs, start=1):
            path: Path = self.context[path_key]
            atomic_output(path, self.context[key].write_csv)
            self.report_progress(index / len(outputs) * 95)
        self.logger.info(
            f"Factor analysis outputs written result={self.context['result_path']} "
            f"quantiles={self.context['quantiles_path']} rows={self.context['results'].height}",
        )

    def write_metadata(self) -> None:
        output_dir: Path = self.context["output_dir"]
        dataset_record = artifact_record(self.context["dataset_path"], output_dir)
        self.report_progress(35)
        result_record = artifact_record(self.context["result_path"], output_dir)
        self.report_progress(60)
        quantiles_record = artifact_record(self.context["quantiles_path"], output_dir)
        self.report_progress(85)
        metadata = {
            **metadata_header(
                task_name="alpha158_factor_analysis",
                task_id=self.task_id,
                task_type=self.task_type.value,
            ),
            "config": self.config.model_dump(mode="json", exclude={"task_id", "task_type"}),
            "source": {
                "etl_task_id": self.config.etl_task_id,
                "metadata": str(self.context["source_metadata_path"]),
                "dataset_sha256": dataset_record["sha256"],
            },
            "feature_count": len(self.context["features"]),
            "labels": list(LABELS),
            "rows": self.context["results"].height,
            "definitions": {
                "icir": "mean daily cross-sectional Pearson IC divided by its sample standard deviation",
                "rankicir": "mean daily cross-sectional Spearman RankIC divided by its sample standard deviation",
                "quantile_spread": "highest quantile mean raw return minus lowest quantile mean raw return",
                "quantile_monotonicity": "Spearman correlation between quantile order and mean raw return",
                "sample_filter": "is_buyable" if self.config.tradable_only else "none",
            },
            "artifacts": {
                "result": "factor_analysis.csv",
                "quantiles": "factor_quantiles.csv",
            },
            "artifact_integrity": {
                "result": result_record,
                "quantiles": quantiles_record,
            },
        }
        write_metadata(self.context["metadata_path"], metadata)
        self.report_progress(95)

    def publish_output(self) -> None:
        self.context.update(
            result_file=str(self.context["result_path"]),
            quantiles_file=str(self.context["quantiles_path"]),
            metadata_file=str(self.context["metadata_path"]),
            rows=self.context["results"].height,
        )
