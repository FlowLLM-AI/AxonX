"""Pure Polars calculations for Alpha158 factor diagnostics."""

from __future__ import annotations

import polars as pl

from .etl_pipeline import LABELS


class FactorMetricsCalculator:
    """Calculate factor IC and quantile diagnostics for one feature batch."""

    def __init__(self, minimum_daily_samples: int, quantiles: int):
        self.minimum_daily_samples = minimum_daily_samples
        self.quantiles = quantiles

    def analyze_batch(
        self,
        frame: pl.DataFrame,
        features: tuple[str, ...],
    ) -> tuple[pl.DataFrame, pl.DataFrame]:
        """Calculate daily IC and quantile summaries for a feature batch."""
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
                        pl.col("factor_value").is_finite() & pl.col("label_value").is_finite(),
                    )
                )
                daily = (
                    valid.group_by("trade_date")
                    .agg(
                        pl.len().alias("samples"),
                        pl.corr("factor_value", "label_value", method="pearson").alias(
                            "ic",
                        ),
                        pl.corr("factor_value", "label_value", method="spearman").alias(
                            "rank_ic",
                        ),
                    )
                    .filter(pl.col("samples") >= self.minimum_daily_samples)
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
                    ),
                )
                quantile_plans.append(self._quantile_plan(valid, feature, label))

        daily_metrics, quantiles = pl.collect_all(
            [
                self._finalize_daily_metrics(pl.concat(daily_plans)),
                pl.concat(quantile_plans),
            ],
        )
        quantile_summary = (
            quantiles.lazy()
            .group_by("factor", "label")
            .agg(
                (
                    pl.col("mean_return").filter(pl.col("quantile") == self.quantiles).first()
                    - pl.col("mean_return").filter(pl.col("quantile") == 1).first()
                ).alias("quantile_spread"),
                pl.corr("quantile", "mean_return", method="spearman").alias(
                    "quantile_monotonicity",
                ),
            )
        )
        results = (
            daily_metrics.lazy()
            .with_columns(
                (pl.col("valid_samples") / frame.height if frame.height else pl.lit(0.0)).alias("coverage"),
            )
            .join(quantile_summary, on=["factor", "label"], how="left")
            .with_columns(
                pl.col("quantile_spread", "quantile_monotonicity").fill_null(
                    float("nan"),
                ),
                pl.when(pl.col("rankic_mean").is_finite())
                .then(
                    pl.when(pl.col("rankic_mean") >= 0).then(pl.lit("positive")).otherwise(pl.lit("negative")),
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
        self,
        valid: pl.LazyFrame,
        feature: str,
        label: str,
    ) -> pl.LazyFrame:
        daily_size = pl.len().over("trade_date")
        return (
            valid.filter(daily_size >= self.minimum_daily_samples)
            .with_columns(
                (
                    (
                        (pl.col("factor_value").rank(method="average").over("trade_date") - 1)
                        / daily_size
                        * self.quantiles
                    )
                    .floor()
                    .clip(0, self.quantiles - 1)
                    .cast(pl.Int16)
                    .add(1)
                    .alias("quantile")
                ),
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
                    f"rankic_{name}",
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
                    "rankic_t_stat",
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
                ).fill_null(nan),
            )
        )
