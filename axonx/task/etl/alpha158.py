"""Build a compact Alpha158 dataset from DownloadTushareTask output."""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

import polars as pl
from pydantic import field_validator

from ...components.registry import R
from ...enums import TaskType
from ..base import BaseConfig, BaseTask, TaskStep

WINDOWS = (5, 10, 20, 30, 60)
KBAR = ("KMID", "KLEN", "KMID2", "KUP", "KUP2", "KLOW", "KLOW2", "KSFT", "KSFT2")
PRICE = ("OPEN0", "HIGH0", "LOW0", "VWAP0")
ROLLING = (
    "ROC",
    "MA",
    "STD",
    "BETA",
    "RSQR",
    "RESI",
    "MAX",
    "MIN",
    "QTLU",
    "QTLD",
    "RANK",
    "RSV",
    "IMAX",
    "IMIN",
    "IMXD",
    "CORR",
    "CORD",
    "CNTP",
    "CNTN",
    "CNTD",
    "SUMP",
    "SUMN",
    "SUMD",
    "VMA",
    "VSTD",
    "WVMA",
    "VSUMP",
    "VSUMN",
    "VSUMD",
)
RAW_FEATURES = (
    *KBAR,
    *PRICE,
    *(f"{name}{window}" for name in ROLLING for window in WINDOWS),
)
FEATURES = tuple(f"f_alpha158_{name}" for name in RAW_FEATURES)
LABELS = tuple(f"label_{horizon}d" for horizon in range(1, 6))
EPSILON = 1e-12


class Alpha158Config(BaseConfig):
    """Configure input partitions, output file, and optional output date range."""

    input_dir: Path = Path("tushare")
    output_file: Path = Path("etl/alpha158.parquet")
    start_date: str | None = None
    end_date: str | None = None

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def normalize_date(cls, value: object) -> object:
        return (
            str(value)
            if isinstance(value, int) and not isinstance(value, bool)
            else value
        )


@R.register("alpha158_etl")
class Alpha158Task(BaseTask):
    """Create adjusted Alpha158 features, 1-5 trading-day close returns, and HS300 weights.

    The task consumes ``tushare/<year>/<trade_date>/{daily,adj_factor,index_weight}.parquet`` partitions.
    Features at date t only use observations through t. ``label_1d`` through ``label_5d`` are cumulative adjusted
    close returns from t to the corresponding future market trading day; a label is null when its target quote is
    unavailable. HS300 weights use the latest snapshot on or before t and are stored as decimal weights.
    """

    config_cls = Alpha158Config
    config: Alpha158Config
    task_type = TaskType.ETL
    output_keys = ("output_file", "rows", "feature_count")

    def build_task_steps(self) -> Iterable[TaskStep]:
        yield self.resolve_paths
        yield self.build_dataset
        yield self.write_output

    def resolve_paths(self) -> None:
        input_dir = self.resolve_workspace_path(self.config.input_dir)
        daily_files = sorted(input_dir.glob("*/*/daily.parquet"))
        factor_files = sorted(input_dir.glob("*/*/adj_factor.parquet"))
        weight_files = sorted(input_dir.glob("*/*/index_weight.parquet"))
        if not daily_files or not factor_files:
            raise FileNotFoundError(f"缺少 daily 或 adj_factor 分区: {input_dir}")
        if (
            self.config.start_date
            and self.config.end_date
            and self.config.start_date > self.config.end_date
        ):
            raise ValueError("start_date 不能晚于 end_date")
        self.context.update(
            daily_files=daily_files,
            factor_files=factor_files,
            weight_files=weight_files,
            output_path=self.resolve_workspace_path(self.config.output_file),
        )

    def build_dataset(self) -> None:
        daily_columns = (
            "ts_code",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "vol",
            "amount",
        )
        daily = pl.scan_parquet(self.context["daily_files"]).select(
            pl.col("ts_code").cast(pl.String),
            pl.col("trade_date").cast(pl.String),
            *(pl.col(column).cast(pl.Float64) for column in daily_columns[2:]),
        )
        factors = pl.scan_parquet(self.context["factor_files"]).select(
            pl.col("ts_code").cast(pl.String),
            pl.col("trade_date").cast(pl.String),
            pl.col("adj_factor").cast(pl.Float64),
        )
        frame = (
            daily.join(factors, on=["ts_code", "trade_date"], how="left")
            .collect()
            .sort("ts_code", "trade_date")
        )
        if frame.is_empty():
            raise ValueError("daily 与 adj_factor 没有可匹配的数据")
        if frame.select("ts_code", "trade_date").n_unique() != frame.height:
            raise ValueError("输入包含重复的 ts_code, trade_date")
        positive = pl.col("open", "high", "low", "close", "adj_factor")
        nonnegative = pl.col("vol", "amount")
        invalid = (
            ~pl.col("trade_date").str.contains(r"^\d{8}$")
            | pl.any_horizontal(
                positive.is_null(), ~positive.is_finite(), positive <= 0
            )
            | pl.any_horizontal(
                nonnegative.is_null(), ~nonnegative.is_finite(), nonnegative < 0
            )
        )
        if frame.filter(invalid).height:
            raise ValueError("daily 或 adj_factor 包含缺失、非有限或越界数据")

        calendar = (
            frame.select("trade_date")
            .unique()
            .sort("trade_date")
            .with_row_index("_trade_index")
        )
        bounds = frame.group_by("ts_code").agg(
            pl.col("trade_date").min().alias("_first_date"),
            pl.col("trade_date").max().alias("_last_date"),
        )
        frame = (
            bounds.join(calendar, how="cross")
            .filter(
                pl.col("trade_date").is_between(
                    pl.col("_first_date"), pl.col("_last_date")
                )
            )
            .select("ts_code", "trade_date", "_trade_index")
            .join(
                frame.with_columns(pl.lit(True).alias("_has_market_data")),
                on=["ts_code", "trade_date"],
                how="left",
            )
            .with_columns(pl.col("_has_market_data").fill_null(False))
            .sort("ts_code", "_trade_index")
        ).with_columns(
            (pl.col("open") * pl.col("adj_factor")).alias("_open"),
            (pl.col("high") * pl.col("adj_factor")).alias("_high"),
            (pl.col("low") * pl.col("adj_factor")).alias("_low"),
            (pl.col("close") * pl.col("adj_factor")).alias("_close"),
            (pl.col("vol") / pl.col("adj_factor")).alias("_volume"),
            pl.when(pl.col("vol") > 0)
            .then(pl.col("amount") * 10.0 / pl.col("vol") * pl.col("adj_factor"))
            .otherwise(pl.col("close") * pl.col("adj_factor"))
            .alias("_vwap"),
            pl.col("_trade_index").cast(pl.Float64).alias("_x"),
        )
        frame = self._features(frame)
        frame = self._labels(frame)
        frame = self._weights(frame)

        if self.config.start_date:
            frame = frame.filter(pl.col("trade_date") >= self.config.start_date)
        if self.config.end_date:
            frame = frame.filter(pl.col("trade_date") <= self.config.end_date)
        output = (
            frame.filter("_has_market_data")
            .select(
                "trade_date",
                "ts_code",
                *(
                    pl.col(raw).alias(name)
                    for raw, name in zip(RAW_FEATURES, FEATURES, strict=True)
                ),
                *LABELS,
                "index_weight_hs300",
            )
            .sort("trade_date", "ts_code")
        )
        if output.is_empty():
            raise ValueError("输出日期范围内没有数据")
        self.context["output"] = output

    @staticmethod
    def _features(frame: pl.DataFrame) -> pl.DataFrame:
        group = "ts_code"
        spread = pl.col("_high") - pl.col("_low")
        frame = frame.with_columns(
            ((pl.col("_close") - pl.col("_open")) / pl.col("_open")).alias("KMID"),
            (spread / pl.col("_open")).alias("KLEN"),
            ((pl.col("_close") - pl.col("_open")) / (spread + EPSILON)).alias("KMID2"),
            (
                (pl.col("_high") - pl.max_horizontal("_open", "_close"))
                / pl.col("_open")
            ).alias("KUP"),
            (
                (pl.col("_high") - pl.max_horizontal("_open", "_close"))
                / (spread + EPSILON)
            ).alias("KUP2"),
            (
                (pl.min_horizontal("_open", "_close") - pl.col("_low"))
                / pl.col("_open")
            ).alias("KLOW"),
            (
                (pl.min_horizontal("_open", "_close") - pl.col("_low"))
                / (spread + EPSILON)
            ).alias("KLOW2"),
            (
                (2 * pl.col("_close") - pl.col("_high") - pl.col("_low"))
                / pl.col("_open")
            ).alias("KSFT"),
            (
                (2 * pl.col("_close") - pl.col("_high") - pl.col("_low"))
                / (spread + EPSILON)
            ).alias("KSFT2"),
            (pl.col("_open") / pl.col("_close")).alias("OPEN0"),
            (pl.col("_high") / pl.col("_close")).alias("HIGH0"),
            (pl.col("_low") / pl.col("_close")).alias("LOW0"),
            (pl.col("_vwap") / pl.col("_close")).alias("VWAP0"),
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
        for window in WINDOWS:
            frame = Alpha158Task._rolling(frame, window)
        return frame

    @staticmethod
    def _rolling(frame: pl.DataFrame, window: int) -> pl.DataFrame:
        def roll(expr: pl.Expr, method: str, minimum: int = 1) -> pl.Expr:
            return getattr(expr, method)(window_size=window, min_samples=minimum).over(
                "ts_code"
            )

        close, volume, x = pl.col("_close"), pl.col("_volume"), pl.col("_x")
        mean_close, mean_x = roll(close, "rolling_mean"), roll(x, "rolling_mean")
        covariance = pl.rolling_cov(
            close, x, window_size=window, min_samples=2, ddof=1
        ).over("ts_code")
        slope = covariance / roll(x, "rolling_var", 2)
        high, low = (
            roll(pl.col("_high"), "rolling_max"),
            roll(pl.col("_low"), "rolling_min"),
        )
        corr = pl.rolling_corr(
            close, (volume + 1).log(), window_size=window, min_samples=2
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
            lower_bound=0
        ) / (count - 1)
        wvma = pl.when(count > 1).then(variance.sqrt() / (total / count + EPSILON))
        # qlib ArgMax/ArgMin choose the oldest matching extreme in a tied window.
        max_age = pl.max_horizontal(
            *[
                pl.when(pl.col("_high").shift(i).over("ts_code") == high)
                .then(i)
                .otherwise(-1)
                for i in range(window)
            ]
        )
        min_age = pl.max_horizontal(
            *[
                pl.when(pl.col("_low").shift(i).over("ts_code") == low)
                .then(i)
                .otherwise(-1)
                for i in range(window)
            ]
        )
        length = roll(x.is_not_null().cast(pl.Float64), "rolling_sum")
        imax, imin = (length - max_age) / window, (length - min_age) / window
        return frame.with_columns(
            (close.shift(window).over("ts_code") / close).alias(f"ROC{window}"),
            (mean_close / close).alias(f"MA{window}"),
            (roll(close, "rolling_std") / close).alias(f"STD{window}"),
            (slope / close).alias(f"BETA{window}"),
            pl.rolling_corr(close, x, window_size=window, min_samples=2)
            .over("ts_code")
            .pow(2)
            .alias(f"RSQR{window}"),
            ((close - (mean_close + slope * (x - mean_x))) / close).alias(
                f"RESI{window}"
            ),
            (high / close).alias(f"MAX{window}"),
            (low / close).alias(f"MIN{window}"),
            (
                close.rolling_quantile(
                    0.8, interpolation="linear", window_size=window, min_samples=1
                ).over("ts_code")
                / close
            ).alias(f"QTLU{window}"),
            (
                close.rolling_quantile(
                    0.2, interpolation="linear", window_size=window, min_samples=1
                ).over("ts_code")
                / close
            ).alias(f"QTLD{window}"),
            (
                close.rolling_rank(window, method="average", min_samples=1).over(
                    "ts_code"
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
                f"CNTD{window}"
            ),
            (roll(gain, "rolling_sum") / (abs_sum + EPSILON)).alias(f"SUMP{window}"),
            (roll(loss, "rolling_sum") / (abs_sum + EPSILON)).alias(f"SUMN{window}"),
            (
                (roll(gain, "rolling_sum") - roll(loss, "rolling_sum"))
                / (abs_sum + EPSILON)
            ).alias(f"SUMD{window}"),
            (roll(volume, "rolling_mean") / (volume + EPSILON)).alias(f"VMA{window}"),
            (roll(volume, "rolling_std") / (volume + EPSILON)).alias(f"VSTD{window}"),
            wvma.alias(f"WVMA{window}"),
            (roll(vgain, "rolling_sum") / (vabs_sum + EPSILON)).alias(f"VSUMP{window}"),
            (roll(vloss, "rolling_sum") / (vabs_sum + EPSILON)).alias(f"VSUMN{window}"),
            (
                (roll(vgain, "rolling_sum") - roll(vloss, "rolling_sum"))
                / (vabs_sum + EPSILON)
            ).alias(f"VSUMD{window}"),
        )

    @staticmethod
    def _labels(frame: pl.DataFrame) -> pl.DataFrame:
        return frame.with_columns(
            *(
                (
                    pl.col("_close").shift(-horizon).over("ts_code") / pl.col("_close")
                    - 1
                ).alias(label)
                for horizon, label in enumerate(LABELS, start=1)
            ),
        )

    def _weights(self, frame: pl.DataFrame) -> pl.DataFrame:
        if not self.context["weight_files"]:
            return frame.with_columns(
                pl.lit(None, dtype=pl.Float64).alias("index_weight_hs300")
            )
        weights = (
            pl.scan_parquet(self.context["weight_files"])
            .filter(pl.col("index_code") == "000300.SH")
            .select(
                pl.col("trade_date").cast(pl.String).alias("_weight_date"),
                pl.col("con_code").cast(pl.String).alias("ts_code"),
                (pl.col("weight").cast(pl.Float64) / 100).alias("index_weight_hs300"),
            )
            .collect()
        )
        if weights.select("_weight_date", "ts_code").n_unique() != weights.height:
            raise ValueError("index_weight 包含重复的 trade_date, con_code")
        snapshots = weights.select("_weight_date").unique().sort("_weight_date")
        dates = (
            frame.select("trade_date")
            .unique()
            .sort("trade_date")
            .join_asof(
                snapshots,
                left_on="trade_date",
                right_on="_weight_date",
                strategy="backward",
            )
        )
        return (
            frame.join(dates, on="trade_date")
            .join(weights, on=["_weight_date", "ts_code"], how="left")
            .with_columns(
                pl.when(pl.col("_weight_date").is_null())
                .then(None)
                .otherwise(pl.col("index_weight_hs300").fill_null(0))
                .alias("index_weight_hs300"),
            )
        )

    def write_output(self) -> None:
        output: pl.DataFrame = self.context["output"]
        path: Path = self.context["output_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        try:
            output.write_parquet(temporary, compression="zstd")
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        self.context.update(
            output_file=str(path), rows=output.height, feature_count=len(FEATURES)
        )
