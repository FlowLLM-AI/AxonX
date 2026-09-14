"""Analyze every Alpha158 factor against all five realized-return horizons."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import polars as pl
from pydantic import Field

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
from .alpha158_etl import LABELS


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
        source_metadata = read_metadata(
            source_metadata_path, description="Alpha158 ETL"
        )
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
            f"dataset={dataset_path} output_dir={output_dir}"
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
            f"start={stats['start']} end={stats['end']}"
        )

    def calculate_factor_metrics(self) -> None:
        results: list[pl.DataFrame] = []
        quantile_results: list[pl.DataFrame] = []
        features: tuple[str, ...] = self.context["features"]
        total = len(features)
        for offset in range(0, total, self.config.feature_batch_size):
            batch = features[offset : offset + self.config.feature_batch_size]
            columns = ("trade_date", *batch, *LABELS)
            if self.config.tradable_only:
                columns = (*columns, "is_buyable")
            source = pl.scan_parquet(self.context["dataset_path"]).select(columns)
            if self.config.tradable_only:
                source = source.filter("is_buyable").drop("is_buyable")
            frame = source.collect()
            batch_results, batch_quantiles = self._analyze_batch(frame, batch)
            results.append(batch_results)
            quantile_results.append(batch_quantiles)
            completed = min(offset + len(batch), total)
            percentage = completed / total * 95
            self.report_progress(percentage)
            self.logger.info(
                f"Factor diagnostics progress completed={completed}/{total} last_factor={batch[-1]}"
            )
        self.context["results"] = pl.concat(results, how="vertical")
        self.context["quantile_results"] = pl.concat(
            quantile_results, how="vertical"
        ).sort("factor", "label", "quantile")

    def _analyze_batch(
        self,
        frame: pl.DataFrame,
        features: tuple[str, ...],
    ) -> tuple[pl.DataFrame, pl.DataFrame]:
        daily_plans: list[pl.LazyFrame] = []
        quantile_plans: list[pl.LazyFrame] = []
        for feature in features:
            for label in LABELS:
                valid = (
                    frame.lazy()
                    .select(
                        "trade_date",
                        pl.col(feature).alias("factor_value"),
                        pl.col(label).alias("label_value"),
                    )
                    .filter(
                        pl.col("factor_value").is_finite()
                        & pl.col("label_value").is_finite()
                    )
                )
                daily = (
                    valid.group_by("trade_date")
                    .agg(
                        pl.len().alias("samples"),
                        pl.corr("factor_value", "label_value", method="pearson").alias(
                            "ic"
                        ),
                        pl.corr("factor_value", "label_value", method="spearman").alias(
                            "rank_ic"
                        ),
                    )
                    .filter(pl.col("samples") >= self.config.minimum_daily_samples)
                )
                daily_plans.append(
                    valid.select(pl.len().alias("valid_samples")).join(
                        daily.select(
                            pl.lit(feature).alias("factor"),
                            pl.lit(label).alias("label"),
                            pl.len().alias("valid_days"),
                            *self._summary_expressions("ic", "ic"),
                            *self._summary_expressions("rank_ic", "rankic"),
                        ),
                        how="cross",
                    )
                )
                quantile_plans.append(self._quantile_plan(valid, feature, label))

        daily_metrics, quantiles = pl.collect_all(
            [
                self._finalize_daily_metrics(pl.concat(daily_plans)),
                pl.concat(quantile_plans),
            ]
        )
        quantile_summary = (
            quantiles.lazy()
            .group_by("factor", "label")
            .agg(
                (
                    pl.col("mean_return")
                    .filter(pl.col("quantile") == self.config.quantiles)
                    .first()
                    - pl.col("mean_return").filter(pl.col("quantile") == 1).first()
                ).alias("quantile_spread"),
                pl.corr("quantile", "mean_return", method="spearman").alias(
                    "quantile_monotonicity"
                ),
            )
        )
        results = (
            daily_metrics.lazy()
            .with_columns(
                (
                    pl.col("valid_samples") / frame.height
                    if frame.height
                    else pl.lit(0.0)
                ).alias("coverage")
            )
            .join(quantile_summary, on=["factor", "label"], how="left")
            .with_columns(
                pl.col("quantile_spread", "quantile_monotonicity").fill_null(
                    float("nan")
                ),
                pl.when(pl.col("rankic_mean").is_finite())
                .then(
                    pl.when(pl.col("rankic_mean") >= 0)
                    .then(pl.lit("positive"))
                    .otherwise(pl.lit("negative"))
                )
                .otherwise(pl.lit("unknown"))
                .alias("direction"),
            )
            .select(
                "factor",
                "label",
                "valid_samples",
                "coverage",
                "valid_days",
                "ic_mean",
                "ic_std",
                "icir",
                "ic_t_stat",
                "ic_positive_rate",
                "rankic_mean",
                "rankic_std",
                "rankicir",
                "rankic_t_stat",
                "rankic_positive_rate",
                "rankic_p05",
                "rankic_p50",
                "rankic_p95",
                "quantile_spread",
                "quantile_monotonicity",
                "direction",
            )
            .collect()
        )
        return results, quantiles

    def _quantile_plan(
        self, valid: pl.LazyFrame, feature: str, label: str
    ) -> pl.LazyFrame:
        daily_size = pl.len().over("trade_date")
        return (
            valid.filter(daily_size >= self.config.minimum_daily_samples)
            .with_columns(
                (
                    (
                        (
                            pl.col("factor_value")
                            .rank(method="average")
                            .over("trade_date")
                            - 1
                        )
                        / daily_size
                        * self.config.quantiles
                    )
                    .floor()
                    .clip(0, self.config.quantiles - 1)
                    .cast(pl.Int16)
                    .add(1)
                    .alias("quantile")
                )
            )
            .group_by("trade_date", "quantile")
            .agg(
                pl.col("label_value").mean().alias("daily_return"),
                pl.len().alias("samples"),
            )
            .group_by("quantile")
            .agg(
                pl.col("daily_return").mean().alias("mean_return"),
                pl.col("daily_return").std(ddof=1).alias("return_std"),
                pl.col("samples").sum().alias("samples"),
                pl.len().alias("days"),
            )
            .with_columns(
                pl.lit(feature).alias("factor"),
                pl.lit(label).alias("label"),
            )
            .select(
                "factor",
                "label",
                "quantile",
                "mean_return",
                "return_std",
                "samples",
                "days",
            )
        )

    @staticmethod
    def _summary_expressions(column: str, prefix: str) -> list[pl.Expr]:
        finite = pl.col(column).filter(pl.col(column).is_finite())
        expressions = [
            finite.len().alias(f"_{prefix}_count"),
            finite.mean().alias(f"{prefix}_mean"),
            finite.std(ddof=1).alias(f"{prefix}_std"),
            (finite > 0).mean().alias(f"{prefix}_positive_rate"),
        ]
        if prefix == "rankic":
            expressions.extend(
                finite.quantile(quantile, interpolation="linear").alias(
                    f"rankic_{name}"
                )
                for name, quantile in (("p05", 0.05), ("p50", 0.50), ("p95", 0.95))
            )
        return expressions

    @staticmethod
    def _finalize_daily_metrics(metrics: pl.LazyFrame) -> pl.LazyFrame:
        nan = float("nan")
        metrics = metrics.with_columns(
            pl.when(pl.col(f"_{prefix}_count") > 0)
            .then(pl.col(f"{prefix}_std").fill_null(0.0))
            .otherwise(nan)
            .alias(f"{prefix}_std")
            for prefix in ("ic", "rankic")
        )
        return (
            metrics.with_columns(
                pl.when(pl.col(f"{prefix}_std") > 0)
                .then(pl.col(f"{prefix}_mean") / pl.col(f"{prefix}_std"))
                .otherwise(0.0)
                .alias(ratio_name)
                for prefix, ratio_name in (("ic", "icir"), ("rankic", "rankicir"))
            )
            .with_columns(
                (pl.col("icir") * pl.col("_ic_count").sqrt()).alias("ic_t_stat"),
                (pl.col("rankicir") * pl.col("_rankic_count").sqrt()).alias(
                    "rankic_t_stat"
                ),
            )
            .with_columns(
                pl.col(
                    "ic_mean",
                    "icir",
                    "ic_t_stat",
                    "ic_positive_rate",
                    "rankic_mean",
                    "rankicir",
                    "rankic_t_stat",
                    "rankic_positive_rate",
                    "rankic_p05",
                    "rankic_p50",
                    "rankic_p95",
                ).fill_null(nan)
            )
        )

    def rank_factors(self) -> None:
        results: pl.DataFrame = self.context["results"]
        self.context["results"] = results.with_columns(
            (
                pl.col("rankic_mean")
                .abs()
                .rank(method="average", descending=True)
                .over("label")
            ).alias("rank_by_abs_rankic"),
            (
                pl.col("rankicir")
                .abs()
                .rank(method="average", descending=True)
                .over("label")
            ).alias("rank_by_abs_rankicir"),
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
            f"quantiles={self.context['quantiles_path']} rows={self.context['results'].height}"
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
            "config": self.config.model_dump(
                mode="json", exclude={"task_id", "task_type"}
            ),
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
