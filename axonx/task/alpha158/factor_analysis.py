"""Analyze every Alpha158 factor against all five realized-return horizons."""

from __future__ import annotations

import math
from collections.abc import Iterable
from pathlib import Path

import numpy as np
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
        required = ("trade_date", "ts_code", *features, *LABELS)
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
        if not stats["rows"]:
            raise ValueError("Alpha158 数据为空")
        self.context.update(features=features, input_stats=stats)
        self.logger.info(
            f"Factor analysis data validated rows={stats['rows']} features={len(features)} "
            f"start={stats['start']} end={stats['end']}"
        )

    def calculate_factor_metrics(self) -> None:
        results: list[dict[str, object]] = []
        quantile_rows: list[dict[str, object]] = []
        features: tuple[str, ...] = self.context["features"]
        total = len(features)
        for offset in range(0, total, self.config.feature_batch_size):
            batch = features[offset : offset + self.config.feature_batch_size]
            frame = pl.read_parquet(
                self.context["dataset_path"], columns=("trade_date", *batch, *LABELS)
            )
            for feature in batch:
                for label in LABELS:
                    result, buckets = self._analyze_pair(frame, feature, label)
                    results.append(result)
                    quantile_rows.extend(buckets)
            completed = min(offset + len(batch), total)
            if offset == 0 or completed == total or completed % 8 == 0:
                percentage = completed / total * 95
                self.report_progress(percentage)
                self.logger.info(
                    f"Factor diagnostics progress completed={completed}/{total} last_factor={batch[-1]}"
                )
        self.context["results"] = pl.DataFrame(results)
        self.context["quantile_results"] = pl.DataFrame(quantile_rows)

    def _analyze_pair(
        self,
        frame: pl.DataFrame,
        feature: str,
        label: str,
    ) -> tuple[dict[str, object], list[dict[str, object]]]:
        valid = frame.select("trade_date", feature, label).filter(
            pl.col(feature).is_finite() & pl.col(label).is_finite(),
        )
        daily = (
            valid.group_by("trade_date")
            .agg(
                pl.len().alias("samples"),
                pl.corr(feature, label, method="pearson").alias("ic"),
                pl.corr(feature, label, method="spearman").alias("rank_ic"),
            )
            .filter(pl.col("samples") >= self.config.minimum_daily_samples)
            .sort("trade_date")
        )
        ic = self._series_summary(
            daily["ic"] if daily.height else pl.Series([], dtype=pl.Float64)
        )
        rank_ic = self._series_summary(
            daily["rank_ic"] if daily.height else pl.Series([], dtype=pl.Float64),
        )

        bucket_rows: list[dict[str, object]] = []
        bucket_means: list[float] = []
        if valid.height:
            bucketed = (
                valid.filter(
                    pl.len().over("trade_date") >= self.config.minimum_daily_samples
                )
                .with_columns(
                    (
                        (
                            (
                                pl.col(feature)
                                .rank(method="average")
                                .over("trade_date")
                                - 1
                            )
                            / pl.len().over("trade_date")
                            * self.config.quantiles
                        )
                        .floor()
                        .clip(0, self.config.quantiles - 1)
                        .cast(pl.Int16)
                        + 1
                    ).alias("quantile"),
                )
                .group_by("trade_date", "quantile")
                .agg(
                    pl.col(label).mean().alias("daily_return"),
                    pl.len().alias("samples"),
                )
                .group_by("quantile")
                .agg(
                    pl.col("daily_return").mean().alias("mean_return"),
                    pl.col("daily_return").std(ddof=1).alias("return_std"),
                    pl.col("samples").sum().alias("samples"),
                    pl.len().alias("days"),
                )
                .sort("quantile")
            )
            values = dict(
                zip(
                    bucketed["quantile"].to_list(),
                    bucketed["mean_return"].to_list(),
                    strict=True,
                )
            )
            bucket_means = [
                values.get(bucket, math.nan)
                for bucket in range(1, self.config.quantiles + 1)
            ]
            for row in bucketed.iter_rows(named=True):
                bucket_rows.append({"factor": feature, "label": label, **row})

        monotonicity = self._ordered_correlation(bucket_means)
        spread = (
            bucket_means[-1] - bucket_means[0]
            if len(bucket_means) == self.config.quantiles
            and np.isfinite(bucket_means[0])
            and np.isfinite(bucket_means[-1])
            else math.nan
        )
        rankic_mean = rank_ic["mean"]
        direction = (
            "unknown"
            if not np.isfinite(rankic_mean)
            else "positive"
            if rankic_mean >= 0
            else "negative"
        )
        return (
            {
                "factor": feature,
                "label": label,
                "valid_samples": valid.height,
                "coverage": valid.height / frame.height if frame.height else 0.0,
                "valid_days": daily.height,
                "ic_mean": ic["mean"],
                "ic_std": ic["std"],
                "icir": ic["ratio"],
                "ic_t_stat": ic["t_stat"],
                "ic_positive_rate": ic["positive_rate"],
                "rankic_mean": rank_ic["mean"],
                "rankic_std": rank_ic["std"],
                "rankicir": rank_ic["ratio"],
                "rankic_t_stat": rank_ic["t_stat"],
                "rankic_positive_rate": rank_ic["positive_rate"],
                "rankic_p05": rank_ic["p05"],
                "rankic_p50": rank_ic["p50"],
                "rankic_p95": rank_ic["p95"],
                "quantile_spread": spread,
                "quantile_monotonicity": monotonicity,
                "direction": direction,
            },
            bucket_rows,
        )

    @staticmethod
    def _series_summary(values: pl.Series) -> dict[str, float]:
        array = values.cast(pl.Float64, strict=False).to_numpy()
        array = array[np.isfinite(array)]
        if not len(array):
            return dict.fromkeys(
                (
                    "mean",
                    "std",
                    "ratio",
                    "t_stat",
                    "positive_rate",
                    "p05",
                    "p50",
                    "p95",
                ),
                math.nan,
            )
        mean = float(array.mean())
        std = float(array.std(ddof=1)) if len(array) > 1 else 0.0
        ratio = mean / std if std > 0 else 0.0
        return {
            "mean": mean,
            "std": std,
            "ratio": ratio,
            "t_stat": ratio * math.sqrt(len(array)) if std > 0 else 0.0,
            "positive_rate": float((array > 0).mean()),
            "p05": float(np.quantile(array, 0.05)),
            "p50": float(np.quantile(array, 0.50)),
            "p95": float(np.quantile(array, 0.95)),
        }

    @staticmethod
    def _ordered_correlation(values: list[float]) -> float:
        array = np.asarray(values, dtype=float)
        valid = np.isfinite(array)
        if valid.sum() < 2 or np.unique(array[valid]).size < 2:
            return math.nan
        ranks = pl.Series(array[valid]).rank(method="average").to_numpy()
        return float(np.corrcoef(np.flatnonzero(valid), ranks)[0, 1])

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
        for key, path_key in (
            ("results", "result_path"),
            ("quantile_results", "quantiles_path"),
        ):
            path: Path = self.context[path_key]
            atomic_output(path, self.context[key].write_csv)
        self.logger.info(
            f"Factor analysis outputs written result={self.context['result_path']} "
            f"quantiles={self.context['quantiles_path']} rows={self.context['results'].height}"
        )

    def write_metadata(self) -> None:
        output_dir: Path = self.context["output_dir"]
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
                "dataset_sha256": artifact_record(
                    self.context["dataset_path"], output_dir
                )["sha256"],
            },
            "feature_count": len(self.context["features"]),
            "labels": list(LABELS),
            "rows": self.context["results"].height,
            "definitions": {
                "icir": "mean daily cross-sectional Pearson IC divided by its sample standard deviation",
                "rankicir": "mean daily cross-sectional Spearman RankIC divided by its sample standard deviation",
                "quantile_spread": "highest quantile mean raw return minus lowest quantile mean raw return",
                "quantile_monotonicity": "Spearman correlation between quantile order and mean raw return",
            },
            "artifacts": {
                "result": "factor_analysis.csv",
                "quantiles": "factor_quantiles.csv",
            },
            "artifact_integrity": {
                "result": artifact_record(self.context["result_path"], output_dir),
                "quantiles": artifact_record(
                    self.context["quantiles_path"], output_dir
                ),
            },
        }
        write_metadata(self.context["metadata_path"], metadata)

    def publish_output(self) -> None:
        self.context.update(
            result_file=str(self.context["result_path"]),
            quantiles_file=str(self.context["quantiles_path"]),
            metadata_file=str(self.context["metadata_path"]),
            rows=self.context["results"].height,
        )
