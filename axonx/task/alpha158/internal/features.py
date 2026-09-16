"""Polars feature expressions and dataset statistics for Alpha158."""

from __future__ import annotations

from collections.abc import Callable

import polars as pl

from .etl_pipeline import EPSILON, FEATURES, LABEL_OUTPUTS, WINDOWS


def price_features(frame: pl.DataFrame) -> pl.DataFrame:
    """Derive daily candlestick and relative price features."""
    spread = pl.col("_high") - pl.col("_low")
    return frame.with_columns(
        ((pl.col("_close") - pl.col("_open")) / pl.col("_open")).alias("KMID"),
        (spread / pl.col("_open")).alias("KLEN"),
        ((pl.col("_close") - pl.col("_open")) / (spread + EPSILON)).alias("KMID2"),
        ((pl.col("_high") - pl.max_horizontal("_open", "_close")) / pl.col("_open")).alias("KUP"),
        ((pl.col("_high") - pl.max_horizontal("_open", "_close")) / (spread + EPSILON)).alias("KUP2"),
        ((pl.min_horizontal("_open", "_close") - pl.col("_low")) / pl.col("_open")).alias("KLOW"),
        ((pl.min_horizontal("_open", "_close") - pl.col("_low")) / (spread + EPSILON)).alias("KLOW2"),
        ((2 * pl.col("_close") - pl.col("_high") - pl.col("_low")) / pl.col("_open")).alias("KSFT"),
        ((2 * pl.col("_close") - pl.col("_high") - pl.col("_low")) / (spread + EPSILON)).alias("KSFT2"),
        (pl.col("_open") / pl.col("_close")).alias("OPEN0"),
        (pl.col("_high") / pl.col("_close")).alias("HIGH0"),
        (pl.col("_low") / pl.col("_close")).alias("LOW0"),
        (pl.col("_vwap") / pl.col("_close")).alias("VWAP0"),
    )


def rolling_inputs(frame: pl.DataFrame) -> pl.DataFrame:
    """Prepare lagged prices and volumes shared by rolling features."""
    group = "ts_code"
    return frame.with_columns(
        pl.col("_close").shift(1).over(group).alias("_prev_close"),
        pl.col("_volume").shift(1).over(group).alias("_prev_volume"),
    ).with_columns(
        (pl.col("_close") - pl.col("_prev_close")).alias("_dp"),
        (pl.col("_volume") - pl.col("_prev_volume")).alias("_dv"),
        (pl.col("_close") / pl.col("_prev_close")).alias("_close_ratio"),
        pl.when(pl.col("_prev_volume") > 0)
        .then((pl.col("_volume") / pl.col("_prev_volume") + 1).log())
        .alias("_volume_ratio"),
    )


def all_features(frame: pl.DataFrame) -> pl.DataFrame:
    """Build all features in one call for callers that use the helper directly."""
    frame = rolling_inputs(price_features(frame))
    for window in WINDOWS:
        frame = rolling_features(frame, window)
    return frame


def rolling_features(
    frame: pl.DataFrame | pl.LazyFrame,
    window: int,
) -> pl.DataFrame | pl.LazyFrame:
    """Derive the Alpha158 rolling feature family for one window."""

    def roll(expr: pl.Expr, method: str, minimum: int = 1) -> pl.Expr:
        return getattr(expr, method)(window_size=window, min_samples=minimum).over(
            "ts_code",
        )

    close, volume, x = pl.col("_close"), pl.col("_volume"), pl.col("_x")
    mean_close, mean_x = roll(close, "rolling_mean"), roll(x, "rolling_mean")
    covariance = pl.rolling_cov(
        close,
        x,
        window_size=window,
        min_samples=2,
        ddof=1,
    ).over("ts_code")
    slope = covariance / roll(x, "rolling_var", 2)
    high, low = (
        roll(pl.col("_high"), "rolling_max"),
        roll(pl.col("_low"), "rolling_min"),
    )
    corr = pl.rolling_corr(
        close,
        (volume + 1).log(),
        window_size=window,
        min_samples=2,
    ).over("ts_code")
    cord = pl.rolling_corr(
        pl.col("_close_ratio"),
        pl.col("_volume_ratio"),
        window_size=window,
        min_samples=2,
    ).over("ts_code")
    up = (close > pl.col("_prev_close")).fill_null(False).cast(pl.Float64)
    down = (close < pl.col("_prev_close")).fill_null(False).cast(pl.Float64)
    gain, loss = (
        pl.col("_dp").clip(lower_bound=0),
        (-pl.col("_dp")).clip(lower_bound=0),
    )
    vgain, vloss = (
        pl.col("_dv").clip(lower_bound=0),
        (-pl.col("_dv")).clip(lower_bound=0),
    )
    abs_sum, vabs_sum = (
        roll(pl.col("_dp").abs(), "rolling_sum"),
        roll(pl.col("_dv").abs(), "rolling_sum"),
    )
    weighted = (pl.col("_close_ratio") - 1).abs() * volume
    count, total = (
        roll(weighted.is_not_null().cast(pl.Float64), "rolling_sum"),
        roll(weighted, "rolling_sum"),
    )
    variance = (roll(weighted.pow(2), "rolling_sum") - total.pow(2) / count).clip(
        lower_bound=0,
    ) / (count - 1)
    wvma = pl.when(count > 1).then(variance.sqrt() / (total / count + EPSILON))
    # qlib ArgMax/ArgMin choose the oldest matching extreme in a tied window.
    max_age = pl.max_horizontal(
        *[pl.when(pl.col("_high").shift(i).over("ts_code") == high).then(i).otherwise(-1) for i in range(window)],
    )
    min_age = pl.max_horizontal(
        *[pl.when(pl.col("_low").shift(i).over("ts_code") == low).then(i).otherwise(-1) for i in range(window)],
    )
    length = roll(x.is_not_null().cast(pl.Float64), "rolling_sum")
    imax, imin = (length - max_age) / window, (length - min_age) / window
    return frame.with_columns(
        (close.shift(window).over("ts_code") / close).alias(f"ROC{window}"),
        (mean_close / close).alias(f"MA{window}"),
        (roll(close, "rolling_std") / close).alias(f"STD{window}"),
        (slope / close).alias(f"BETA{window}"),
        pl.rolling_corr(close, x, window_size=window, min_samples=2).over("ts_code").pow(2).alias(f"RSQR{window}"),
        ((close - (mean_close + slope * (x - mean_x))) / close).alias(
            f"RESI{window}",
        ),
        (high / close).alias(f"MAX{window}"),
        (low / close).alias(f"MIN{window}"),
        (
            close.rolling_quantile(
                0.8,
                interpolation="linear",
                window_size=window,
                min_samples=1,
            ).over("ts_code")
            / close
        ).alias(f"QTLU{window}"),
        (
            close.rolling_quantile(
                0.2,
                interpolation="linear",
                window_size=window,
                min_samples=1,
            ).over("ts_code")
            / close
        ).alias(f"QTLD{window}"),
        (
            close.rolling_rank(window, method="average", min_samples=1).over(
                "ts_code",
            )
            / roll(close.is_not_null().cast(pl.Float64), "rolling_sum")
        ).alias(f"RANK{window}"),
        ((close - low) / (high - low + EPSILON)).alias(f"RSV{window}"),
        imax.alias(f"IMAX{window}"),
        imin.alias(f"IMIN{window}"),
        (imax - imin).alias(f"IMXD{window}"),
        corr.clip(-1, 1).alias(f"CORR{window}"),
        cord.clip(-1, 1).alias(f"CORD{window}"),
        roll(up, "rolling_mean").alias(f"CNTP{window}"),
        roll(down, "rolling_mean").alias(f"CNTN{window}"),
        (roll(up, "rolling_mean") - roll(down, "rolling_mean")).alias(
            f"CNTD{window}",
        ),
        (roll(gain, "rolling_sum") / (abs_sum + EPSILON)).alias(f"SUMP{window}"),
        (roll(loss, "rolling_sum") / (abs_sum + EPSILON)).alias(f"SUMN{window}"),
        ((roll(gain, "rolling_sum") - roll(loss, "rolling_sum")) / (abs_sum + EPSILON)).alias(f"SUMD{window}"),
        (roll(volume, "rolling_mean") / (volume + EPSILON)).alias(f"VMA{window}"),
        (roll(volume, "rolling_std") / (volume + EPSILON)).alias(f"VSTD{window}"),
        wvma.alias(f"WVMA{window}"),
        (roll(vgain, "rolling_sum") / (vabs_sum + EPSILON)).alias(f"VSUMP{window}"),
        (roll(vloss, "rolling_sum") / (vabs_sum + EPSILON)).alias(f"VSUMN{window}"),
        ((roll(vgain, "rolling_sum") - roll(vloss, "rolling_sum")) / (vabs_sum + EPSILON)).alias(f"VSUMD{window}"),
    )


def dataset_statistics(
    output: pl.DataFrame,
    *,
    progress: Callable[[float], None] | None = None,
) -> pl.DataFrame:
    """Summarize every public value column through parallel Polars plans."""
    total = output.height
    columns = (*FEATURES, *LABEL_OUTPUTS)
    plans: list[pl.LazyFrame] = []
    for column in columns:
        value = pl.col(column).cast(pl.Float64, strict=False)
        finite_value = pl.when(value.is_finite()).then(value)
        plans.append(
            output.lazy().select(
                pl.lit(column).alias("column"),
                pl.lit(total).alias("total_count"),
                value.is_not_null().sum().alias("non_null_count"),
                value.is_nan().sum().alias("nan_count"),
                value.is_infinite().sum().alias("inf_count"),
                value.is_finite().sum().alias("finite_count"),
                finite_value.min().alias("min"),
                finite_value.quantile(0.03, interpolation="linear").alias("p03"),
                finite_value.quantile(0.50, interpolation="linear").alias("p50"),
                finite_value.quantile(0.97, interpolation="linear").alias("p97"),
                finite_value.max().alias("max"),
                finite_value.mean().alias("mean"),
                finite_value.std(ddof=0).alias("std"),
                finite_value.drop_nulls().n_unique().alias("unique_count"),
                (finite_value == 0).sum().alias("zero_count"),
            ),
        )
    summaries = []
    batch_size = 16
    for offset in range(0, len(plans), batch_size):
        summaries.extend(pl.collect_all(plans[offset : offset + batch_size]))
        if progress is not None:
            progress(min(offset + batch_size, len(plans)) / len(plans) * 95)
    result = (
        pl.concat(summaries)
        .with_columns(
            (pl.col("total_count") - pl.col("non_null_count")).alias("null_count"),
        )
        .with_columns(
            (pl.col(name) / pl.col("total_count")).alias(rate)
            for name, rate in (
                ("finite_count", "finite_rate"),
                ("null_count", "null_rate"),
                ("nan_count", "nan_rate"),
                ("inf_count", "inf_rate"),
                ("zero_count", "zero_rate"),
            )
        )
        .select(
            "column",
            "total_count",
            "finite_count",
            "null_count",
            "nan_count",
            "inf_count",
            "finite_rate",
            "null_rate",
            "nan_rate",
            "inf_rate",
            "zero_rate",
            "min",
            "p03",
            "p50",
            "p97",
            "max",
            "mean",
            "std",
            "unique_count",
        )
    )
    return result
