"""Build a compact Alpha158 dataset from DownloadTushareTask output."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from pathlib import Path

import polars as pl
from pydantic import Field, field_validator

from ...components.registry import R
from ...enums import TaskType
from ..base import BaseConfig, BaseTask, TaskStep
from ._artifacts import artifact_record, metadata_header, write_metadata

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
CSZ_LABELS = tuple(f"{label}_csz" for label in LABELS)
RANK_LABELS = tuple(f"{label}_rank" for label in LABELS)
VALID_LABELS = tuple(f"{label}_is_valid" for label in LABELS)
LABEL_OUTPUTS = tuple(
    column for columns in zip(LABELS, CSZ_LABELS, RANK_LABELS, VALID_LABELS, strict=True) for column in columns
)
EPSILON = 1e-12
HISTORY_DAYS = max(WINDOWS)
ST_LIMIT_CHANGE_DATE = "20260706"
MARKET_STATE_COLUMNS = (
    "name",
    "list_date",
    "delist_date",
    "is_st",
    "is_delisting",
    "is_limit_up",
    "is_limit_down",
    "is_insufficient_history",
    "is_buyable",
)


class Alpha158Config(BaseConfig):
    """Configure input partitions, output file, and optional output date range."""

    input_dir: Path = Path("tushare")
    output_file: Path | None = None
    start_date: str | None = "20140101"
    end_date: str | None = None
    csz_winsorize_tail: float = Field(
        default=0.025,
        ge=0.0,
        lt=0.5,
        description="Fraction clipped from each cross-sectional tail before label z-scoring",
    )
    min_history_coverage: float = Field(default=0.8, gt=0.0, le=1.0)

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def normalize_date(cls, value: object) -> object:
        return str(value) if isinstance(value, int) and not isinstance(value, bool) else value


@R.register("alpha158_etl")
class Alpha158Task(BaseTask):
    """Create adjusted Alpha158 features, 1-5 trading-day close returns, and HS300 weights.

    The task consumes Tushare quotes, adjustments, limits, index weights, calendar, and stock identity data.
    Features at date t only use observations through t. ``label_1d`` through ``label_5d`` are cumulative adjusted
    close returns from t to the corresponding future market trading day; a label is null when its target quote is
    unavailable. CSZ labels are winsorized by date before z-scoring. HS300 weights use the latest snapshot on or
    before t and are stored as decimal weights.
    """

    config_cls = Alpha158Config
    config: Alpha158Config
    task_type = TaskType.ETL
    output_keys = (
        "output_file",
        "statistics_file",
        "metadata_file",
        "rows",
        "feature_count",
    )

    def build_task_steps(self) -> Iterable[TaskStep]:
        yield self.resolve_paths
        yield self.load_and_validate_market_data
        yield self.build_trading_panel
        yield self.calculate_base_features
        yield self.calculate_rolling_features
        yield self.attach_market_status
        yield self.calculate_labels
        yield self.attach_index_weights
        yield self.finalize_dataset
        yield self.calculate_statistics
        yield self.write_outputs
        yield self.write_metadata
        yield self.publish_output

    def resolve_paths(self) -> None:
        input_dir = self.resolve_workspace_path(self.config.input_dir)
        daily_files = sorted(input_dir.glob("*/*/daily.parquet"))
        factor_files = sorted(input_dir.glob("*/*/adj_factor.parquet"))
        weight_files = sorted(input_dir.glob("*/*/index_weight.parquet"))
        static_files = {name: input_dir / f"{name}.parquet" for name in ("trade_cal", "stock_basic", "namechange")}
        if not daily_files or not factor_files:
            raise FileNotFoundError(f"缺少 daily 或 adj_factor 分区: {input_dir}")
        missing = [path for path in static_files.values() if not path.is_file()]
        if missing:
            raise FileNotFoundError(f"缺少 Alpha158 主数据: {', '.join(map(str, missing))}")
        if self.config.start_date and self.config.end_date and self.config.start_date > self.config.end_date:
            raise ValueError("start_date 不能晚于 end_date")
        output_path = (
            self.resolve_workspace_path(self.config.output_file)
            if self.config.output_file is not None
            else self.workspace_path / "etl" / self.task_id / "alpha158.parquet"
        )
        statistics_path = output_path.with_suffix(".csv")
        if statistics_path == output_path:
            raise ValueError("output_file 必须使用非 CSV 扩展名")
        self.context.update(
            daily_files=daily_files,
            factor_files=factor_files,
            weight_files=weight_files,
            limit_files=sorted(input_dir.glob("*/*/stk_limit.parquet")),
            **{f"{name}_file": path for name, path in static_files.items()},
            output_path=output_path,
            statistics_path=statistics_path,
            task_dir=self.workspace_path / "etl" / self.task_id,
            metadata_path=self.workspace_path / "etl" / self.task_id / "metadata.json",
        )
        self.logger.info(
            f"Alpha158 paths resolved input_dir={input_dir} "
            f"daily_files={len(daily_files)} factor_files={len(factor_files)} "
            f"weight_files={len(weight_files)} output_file={output_path}",
        )

    def load_and_validate_market_data(self) -> None:
        """Load the quote and adjustment-factor partitions and validate their rows."""
        daily_columns = (
            "ts_code",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "pre_close",
            "vol",
            "amount",
        )
        daily = (
            pl.scan_parquet(self.context["daily_files"])
            .select(
                pl.col("ts_code").cast(pl.String),
                pl.col("trade_date").cast(pl.String),
                *(pl.col(column).cast(pl.Float64) for column in daily_columns[2:]),
            )
            .filter(~pl.col("ts_code").str.ends_with(".BJ"))
        )
        factors = (
            pl.scan_parquet(self.context["factor_files"])
            .select(
                pl.col("ts_code").cast(pl.String),
                pl.col("trade_date").cast(pl.String),
                pl.col("adj_factor").cast(pl.Float64),
            )
            .filter(~pl.col("ts_code").str.ends_with(".BJ"))
        )
        frame = daily.join(factors, on=["ts_code", "trade_date"], how="left").collect().sort("ts_code", "trade_date")
        self.report_progress(70)
        if frame.is_empty():
            raise ValueError("daily 与 adj_factor 没有可匹配的数据")
        if frame.select("ts_code", "trade_date").n_unique() != frame.height:
            raise ValueError("输入包含重复的 ts_code, trade_date")
        missing_adj_factor_rows = frame["adj_factor"].null_count()
        if missing_adj_factor_rows:
            fallback = (
                pl.col("adj_factor").shift(-1).over("ts_code")
                * pl.col("pre_close").shift(-1).over("ts_code")
                / pl.col("close")
            )
            frame = frame.with_columns(pl.coalesce("adj_factor", fallback).alias("adj_factor"))
        unresolved_adj_factor_rows = frame["adj_factor"].null_count()
        self.context["filled_adj_factor_rows"] = missing_adj_factor_rows - unresolved_adj_factor_rows
        self.logger.info(
            f"Adjustment factors checked missing_rows={missing_adj_factor_rows} "
            f"filled_rows={self.context['filled_adj_factor_rows']} "
            f"unresolved_rows={unresolved_adj_factor_rows}",
        )
        self.report_progress(80)
        positive = pl.col("open", "high", "low", "close", "adj_factor")
        nonnegative = pl.col("vol", "amount")
        invalid = (
            ~pl.col("trade_date").str.contains(r"^\d{8}$")
            | pl.any_horizontal(
                positive.is_null(),
                ~positive.is_finite(),
                positive <= 0,
            )
            | pl.any_horizontal(
                nonnegative.is_null(),
                ~nonnegative.is_finite(),
                nonnegative < 0,
            )
        )
        if frame.filter(invalid).height:
            raise ValueError("daily 或 adj_factor 包含缺失、非有限或越界数据")
        self.context["frame"] = frame
        self.report_progress(95)
        self.logger.info(
            f"Market data loaded rows={frame.height} "
            f"symbols={frame['ts_code'].n_unique()} "
            f"start_date={frame['trade_date'].min()} end_date={frame['trade_date'].max()}",
        )

    def load_reference_data(self) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
        """Load the authoritative calendar, stock lifecycle, and historical names."""
        calendar = (
            pl.read_parquet(self.context["trade_cal_file"], columns=("cal_date", "is_open"))
            .with_columns(pl.col("cal_date").cast(pl.String), pl.col("is_open").cast(pl.Int8))
            .filter(pl.col("is_open") == 1)
            .select(pl.col("cal_date").alias("trade_date"))
            .unique()
            .sort("trade_date")
        )
        stocks = (
            pl.read_parquet(
                self.context["stock_basic_file"],
                columns=("ts_code", "name", "list_date", "delist_date"),
            )
            .with_columns(pl.col("ts_code", "name", "list_date", "delist_date").cast(pl.String))
            .with_columns(
                pl.when(pl.col("delist_date") == "").then(None).otherwise(pl.col("delist_date")).alias("delist_date"),
            )
        )
        names = (
            pl.read_parquet(
                self.context["namechange_file"],
                columns=("ts_code", "name", "start_date", "ann_date"),
            )
            .with_columns(pl.col("ts_code", "name", "start_date", "ann_date").cast(pl.String))
            .with_columns(pl.max_horizontal("start_date", "ann_date").alias("_known_date"))
            .sort("ts_code", "_known_date", "start_date")
            .unique(("ts_code", "_known_date"), keep="last")
        )
        if calendar.is_empty() or stocks.is_empty():
            raise ValueError("trade_cal 或 stock_basic 为空")
        if stocks.select("ts_code").n_unique() != stocks.height:
            raise ValueError("stock_basic 包含重复 ts_code")
        return calendar, stocks, names

    def build_trading_panel(self) -> None:
        """Align every stock to the market calendar and derive adjusted inputs."""
        frame: pl.DataFrame = self.context["frame"]
        calendar, stocks, names = self.load_reference_data()
        calendar = calendar.filter(
            pl.col("trade_date").is_between(
                pl.lit(frame["trade_date"].min()),
                pl.lit(frame["trade_date"].max()),
            ),
        ).with_row_index("_trade_index")
        if calendar.is_empty():
            raise ValueError("行情范围内没有开市日")
        missing_dates = frame.select("trade_date").unique().join(calendar, on="trade_date", how="anti")
        if not missing_dates.is_empty():
            raise ValueError(f"daily 包含非开市日期: {missing_dates.head(5).to_dicts()}")
        quote_bounds = frame.group_by("ts_code").agg(
            pl.col("trade_date").min().alias("_first_trade_date"),
            pl.col("trade_date").max().alias("_last_trade_date"),
        )
        bounds = quote_bounds.join(
            stocks.with_columns(pl.lit(True).alias("_has_stock_basic")),
            on="ts_code",
            how="left",
        ).with_columns(pl.col("_has_stock_basic").fill_null(False))
        missing_stock_basic = bounds.filter(~pl.col("_has_stock_basic"))
        self.context["missing_stock_basic_symbols"] = missing_stock_basic.height
        if not missing_stock_basic.is_empty():
            sample = missing_stock_basic["ts_code"].head(10).to_list()
            self.logger.warning(
                "daily contains symbols absent from stock_basic; inferring lifecycle "
                f"from quote bounds symbols={missing_stock_basic.height} sample={sample}",
            )
        bounds = bounds.with_columns(
            pl.coalesce("name", "ts_code").alias("name"),
            pl.coalesce("list_date", "_first_trade_date").alias("list_date"),
            pl.when(~pl.col("_has_stock_basic"))
            .then(pl.col("_last_trade_date"))
            .otherwise(pl.col("delist_date"))
            .alias("_panel_end_date"),
        ).drop("_first_trade_date", "_last_trade_date", "_has_stock_basic")
        self.report_progress(20)
        frame = (
            bounds.join(calendar, how="cross")
            .filter(
                (pl.col("trade_date") >= pl.col("list_date"))
                & (pl.col("_panel_end_date").is_null() | (pl.col("trade_date") <= pl.col("_panel_end_date"))),
            )
            .drop("_panel_end_date")
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
        self.context.update(stocks=stocks, names=names)
        self.context["frame"] = frame
        self.report_progress(95)
        self.logger.info(
            f"Trading panel built rows={frame.height} "
            f"symbols={frame['ts_code'].n_unique()} calendar_days={calendar.height} "
            f"missing_stock_basic_symbols={self.context['missing_stock_basic_symbols']}",
        )

    def attach_market_status(self) -> None:
        """Attach point-in-time names, official price limits, and a reusable buyability flag."""
        frame: pl.DataFrame = self.context["frame"]
        names: pl.DataFrame = self.context["names"]
        limits = (
            pl.scan_parquet(self.context["limit_files"])
            .select(
                pl.col("ts_code").cast(pl.String),
                pl.col("trade_date").cast(pl.String),
                pl.col("up_limit", "down_limit").cast(pl.Float64),
            )
            .collect()
            if self.context["limit_files"]
            else pl.DataFrame(
                schema={
                    "ts_code": pl.String,
                    "trade_date": pl.String,
                    "up_limit": pl.Float64,
                    "down_limit": pl.Float64,
                },
            )
        )
        self.report_progress(20)
        if limits.select("ts_code", "trade_date").n_unique() != limits.height:
            raise ValueError("stk_limit 包含重复的 ts_code, trade_date")
        historical_names = names.rename({"name": "_historical_name"})
        frame = (
            frame.sort("ts_code", "trade_date")
            .join_asof(
                historical_names,
                by="ts_code",
                left_on="trade_date",
                right_on="_known_date",
                strategy="backward",
                allow_exact_matches=False,
                check_sortedness=False,
            )
            .with_columns(pl.coalesce("_historical_name", "name").alias("name"))
            .join(limits, on=("ts_code", "trade_date"), how="left")
        )
        self.report_progress(45)
        official_limits_valid = (
            pl.col("up_limit").is_finite()
            & pl.col("down_limit").is_finite()
            & (pl.col("up_limit") > pl.col("down_limit"))
        ).fill_null(False)
        is_st_name = pl.col("name").str.to_uppercase().str.contains("ST")
        is_growth_board = (
            pl.col("ts_code").str.starts_with("300")
            | pl.col("ts_code").str.starts_with("301")
            | pl.col("ts_code").str.starts_with("688")
            | pl.col("ts_code").str.starts_with("689")
        )
        limit_rate = (
            pl.when(is_st_name & (pl.col("trade_date") < ST_LIMIT_CHANGE_DATE))
            .then(0.05)
            .when(is_growth_board)
            .then(0.20)
            .otherwise(0.10)
        )
        fallback_up = (pl.col("pre_close") * (1.0 + limit_rate)).round(
            2,
            mode="half_away_from_zero",
        )
        fallback_down = (pl.col("pre_close") * (1.0 - limit_rate)).round(
            2,
            mode="half_away_from_zero",
        )
        frame = frame.with_columns(
            (~official_limits_valid & pl.col("_has_market_data")).alias("_used_limit_fallback"),
            pl.when(official_limits_valid).then(pl.col("up_limit")).otherwise(fallback_up).alias("up_limit"),
            pl.when(official_limits_valid).then(pl.col("down_limit")).otherwise(fallback_down).alias("down_limit"),
        )
        self.report_progress(65)
        observed = (
            pl.col("_has_market_data")
            .cast(pl.Int16)
            .rolling_sum(window_size=HISTORY_DAYS, min_samples=1)
            .over("ts_code")
        )
        history_span = pl.col("_trade_index") - pl.col("_trade_index").min().over("ts_code") + 1
        valid_limits = (
            pl.col("up_limit").is_finite()
            & pl.col("down_limit").is_finite()
            & (pl.col("up_limit") > pl.col("down_limit"))
        )
        upper_name = pl.col("name").str.to_uppercase()
        frame = frame.with_columns(
            upper_name.str.contains(r"^(?:S\*?ST|\*ST|ST)").alias("is_st"),
            pl.col("name").str.contains(r"^退|退$").alias("is_delisting"),
            (valid_limits & (pl.col("close") >= pl.col("up_limit") - 1e-6)).alias("is_limit_up"),
            (valid_limits & (pl.col("close") <= pl.col("down_limit") + 1e-6)).alias("is_limit_down"),
            ((history_span < HISTORY_DAYS) | (observed / HISTORY_DAYS < self.config.min_history_coverage)).alias(
                "is_insufficient_history",
            ),
            valid_limits.alias("_has_valid_limits"),
        ).with_columns(
            (
                pl.col("_has_market_data")
                & pl.col("_has_valid_limits")
                & ~pl.any_horizontal(
                    "is_st",
                    "is_delisting",
                    "is_limit_up",
                    "is_limit_down",
                    "is_insufficient_history",
                )
            ).alias("is_buyable"),
        )
        self.context["missing_limit_rows"] = frame.filter(
            pl.col("_has_market_data") & ~pl.col("_has_valid_limits"),
        ).height
        self.context["fallback_limit_rows"] = frame.filter(
            pl.col("_used_limit_fallback") & pl.col("_has_valid_limits"),
        ).height
        self.context["frame"] = frame
        self.report_progress(95)
        self.logger.info(
            f"Market status attached limit_rows={limits.height} "
            f"fallback_limit_rows={self.context['fallback_limit_rows']} "
            f"missing_limit_rows={self.context['missing_limit_rows']}",
        )

    def calculate_base_features(self) -> None:
        """Calculate candlestick features and inputs shared by rolling features."""
        frame = self._price_features(self.context["frame"])
        self.report_progress(65)
        self.context["frame"] = self._rolling_inputs(frame)
        self.report_progress(95)
        self.logger.info(f"Base features calculated rows={frame.height} features={len(KBAR) + len(PRICE)}")

    def calculate_rolling_features(self) -> None:
        """Calculate independent rolling windows concurrently in Polars."""
        frame: pl.DataFrame = self.context["frame"]
        milestones = (10, 23, 41, 64, 95)
        rolling_frames = []
        for window, percentage in zip(WINDOWS, milestones, strict=True):
            rolling_frames.append(
                self._rolling(frame.lazy(), window).select(*(f"{name}{window}" for name in ROLLING)).collect(),
            )
            self.report_progress(percentage)
            self.logger.info(f"Rolling features calculated window={window} progress={percentage}%")
        rolling_columns = [column for rolling_frame in rolling_frames for column in rolling_frame.get_columns()]
        self.context["frame"] = frame.hstack(rolling_columns)

    def calculate_labels(self) -> None:
        """Calculate forward returns and their cross-sectional transformations."""
        self.logger.info(
            f"Calculating labels horizons={len(LABELS)} " f"winsorize_tail={self.config.csz_winsorize_tail}",
        )
        self.context["frame"] = self._labels(
            self.context["frame"],
            progress=self.report_progress,
        )
        self.logger.info("Labels calculated")

    def attach_index_weights(self) -> None:
        """Attach the latest available HS300 constituent-weight snapshot."""
        self.report_progress(10)
        self.context["frame"] = self._weights(self.context["frame"])
        self.report_progress(95)
        self.logger.info(f"HS300 weights attached files={len(self.context['weight_files'])}")

    def finalize_dataset(self) -> None:
        """Apply the requested date range and project the public output schema."""
        frame: pl.DataFrame = self.context["frame"]

        if self.config.start_date:
            frame = frame.filter(pl.col("trade_date") >= self.config.start_date)
        if self.config.end_date:
            frame = frame.filter(pl.col("trade_date") <= self.config.end_date)
        output = (
            frame.filter("_has_market_data")
            .select(
                "trade_date",
                "ts_code",
                *MARKET_STATE_COLUMNS,
                *(pl.col(raw).alias(name) for raw, name in zip(RAW_FEATURES, FEATURES, strict=True)),
                *LABEL_OUTPUTS,
                "index_weight_hs300",
            )
            .sort("trade_date", "ts_code")
        )
        if output.is_empty():
            raise ValueError("输出日期范围内没有数据")
        self.context["output"] = output
        self.context.pop("frame", None)
        self.report_progress(95)
        self.logger.info(
            f"Dataset finalized rows={output.height} columns={output.width} "
            f"start_date={self.config.start_date or '-'} "
            f"end_date={self.config.end_date or '-'}",
        )

    def calculate_statistics(self) -> None:
        """Calculate data-quality statistics with bounded progress updates."""
        self.context["statistics"] = self._statistics(
            self.context["output"],
            progress=self.report_progress,
        )
        self.logger.info(f"Data-quality statistics calculated " f"columns={self.context['statistics'].height}")

    @staticmethod
    def _price_features(frame: pl.DataFrame) -> pl.DataFrame:
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

    @staticmethod
    def _rolling_inputs(frame: pl.DataFrame) -> pl.DataFrame:
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

    @staticmethod
    def _features(frame: pl.DataFrame) -> pl.DataFrame:
        """Build all features in one call for callers that use the helper directly."""
        frame = Alpha158Task._rolling_inputs(Alpha158Task._price_features(frame))
        for window in WINDOWS:
            frame = Alpha158Task._rolling(frame, window)
        return frame

    @staticmethod
    def _rolling(frame: pl.DataFrame | pl.LazyFrame, window: int) -> pl.DataFrame | pl.LazyFrame:
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

    def _labels(
        self,
        frame: pl.DataFrame,
        *,
        progress: Callable[[float], None] | None = None,
    ) -> pl.DataFrame:
        frame = frame.with_columns(
            *(
                (pl.col("_close").shift(-horizon).over("ts_code") / pl.col("_close") - 1).alias(label)
                for horizon, label in enumerate(LABELS, start=1)
            ),
        )
        frame = frame.with_columns(
            *(
                pl.col(label).is_finite().fill_null(False).alias(valid_label)
                for label, valid_label in zip(LABELS, VALID_LABELS, strict=True)
            ),
        )
        if progress is not None:
            progress(30)
        winsorized_columns: dict[str, str] = {}
        winsorized_expressions: list[pl.Expr] = []
        for label, valid_label in zip(LABELS, VALID_LABELS, strict=True):
            finite = pl.when(pl.col(valid_label)).then(pl.col(label))
            lower = finite.quantile(self.config.csz_winsorize_tail, interpolation="linear").over("trade_date")
            upper = finite.quantile(1 - self.config.csz_winsorize_tail, interpolation="linear").over("trade_date")
            column = f"_{label}_winsorized"
            winsorized_columns[label] = column
            winsorized_expressions.append(finite.clip(lower, upper).alias(column))
        frame = frame.with_columns(*winsorized_expressions)
        if progress is not None:
            progress(60)

        expressions: list[pl.Expr] = []
        for label, csz_label, rank_label, valid_label in zip(
            LABELS,
            CSZ_LABELS,
            RANK_LABELS,
            VALID_LABELS,
            strict=True,
        ):
            finite = pl.when(pl.col(valid_label)).then(pl.col(label))
            winsorized = pl.col(winsorized_columns[label])
            mean = winsorized.mean().over("trade_date")
            std = winsorized.std(ddof=0).over("trade_date")
            count = finite.count().over("trade_date")
            expressions.extend(
                (
                    pl.when(std > EPSILON).then((winsorized - mean) / std).alias(csz_label),
                    pl.when(pl.col(valid_label) & (count > 0))
                    .then(finite.rank(method="average").over("trade_date") / count)
                    .alias(rank_label),
                ),
            )
        frame = frame.with_columns(*expressions)
        if progress is not None:
            progress(95)
        return frame

    def _weights(self, frame: pl.DataFrame) -> pl.DataFrame:
        if not self.context["weight_files"]:
            self.logger.warning("No HS300 weight files found; index weights will be null")
            return frame.with_columns(
                pl.lit(None, dtype=pl.Float64).alias("index_weight_hs300"),
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
        self.logger.info(f"HS300 weight snapshots loaded rows={weights.height} " f"snapshots={snapshots.height}")
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

    def write_outputs(self) -> None:
        output: pl.DataFrame = self.context["output"]
        statistics: pl.DataFrame = self.context["statistics"]
        path: Path = self.context["output_path"]
        statistics_path: Path = self.context["statistics_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        statistics_temporary = statistics_path.with_name(
            f".{statistics_path.name}.{os.getpid()}.tmp",
        )
        try:
            output.write_parquet(temporary, compression="zstd")
            self.report_progress(70)
            statistics.write_csv(statistics_temporary)
            self.report_progress(90)
            temporary.replace(path)
            statistics_temporary.replace(statistics_path)
        finally:
            temporary.unlink(missing_ok=True)
            statistics_temporary.unlink(missing_ok=True)
        self.context.update(
            output_file=str(path),
            statistics_file=str(statistics_path),
            rows=output.height,
            feature_count=len(FEATURES),
        )
        self.logger.info(
            f"Alpha158 outputs written rows={output.height} features={len(FEATURES)} "
            f"dataset_path={path} dataset_bytes={path.stat().st_size} "
            f"statistics_path={statistics_path} "
            f"statistics_bytes={statistics_path.stat().st_size}",
        )

    def write_metadata(self) -> None:
        """Publish the dataset contract used by every downstream Alpha158 task."""
        output: pl.DataFrame = self.context["output"]
        task_dir: Path = self.context["task_dir"]
        task_dir.mkdir(parents=True, exist_ok=True)
        dataset_record = artifact_record(self.context["output_path"], task_dir)
        self.report_progress(45)
        statistics_record = artifact_record(self.context["statistics_path"], task_dir)
        self.report_progress(80)
        metadata = {
            **metadata_header(
                task_name="alpha158_etl",
                task_id=self.task_id,
                task_type=self.task_type.value,
            ),
            "config": self.config.model_dump(mode="json", exclude={"task_id", "task_type"}),
            "date_range": {
                "start": output["trade_date"].min(),
                "end": output["trade_date"].max(),
            },
            "rows": output.height,
            "symbols": output["ts_code"].n_unique(),
            "feature_columns": list(FEATURES),
            "feature_schema": {
                "title": {
                    "zh": "Alpha158 特征结构",
                    "en": "Alpha158 feature schema",
                },
                "groups": [
                    {
                        "name": "基础价量",
                        "features": [f"f_alpha158_{name}" for name in (*KBAR, *PRICE)],
                    },
                    *[
                        {
                            "name": family,
                            "features": [
                                f"f_alpha158_{family}{window}" for window in WINDOWS
                            ],
                        }
                        for family in ROLLING
                    ],
                ],
            },
            "labels": {
                "raw": list(LABELS),
                "csz": list(CSZ_LABELS),
                "rank": list(RANK_LABELS),
                "valid": list(VALID_LABELS),
                "return_unit": "decimal",
                "definition": "adjusted close return from trade_date to the Nth following market trading day",
            },
            "index_weight_columns": ["index_weight_hs300"],
            "market_state_columns": list(MARKET_STATE_COLUMNS),
            "market_state": {
                "buyable_definition": (
                    "listed, quoted, valid limits, non-ST, non-delisting, non-limit, sufficient history"
                ),
                "minimum_history_days": HISTORY_DAYS,
                "minimum_history_coverage": self.config.min_history_coverage,
                "missing_stock_basic_symbols": self.context["missing_stock_basic_symbols"],
                "missing_stock_basic_policy": (
                    "name=ts_code, list_date=first_quote, panel_end=last_quote, delist_date=null"
                ),
                "fallback_limit_rows": self.context["fallback_limit_rows"],
                "missing_limit_rows": self.context["missing_limit_rows"],
            },
            "schema": {name: str(dtype) for name, dtype in output.schema.items()},
            "artifacts": {
                "dataset": dataset_record["path"],
                "statistics": statistics_record["path"],
            },
        }
        metadata["artifact_integrity"] = {
            "dataset": dataset_record,
            "statistics": statistics_record,
        }
        write_metadata(self.context["metadata_path"], metadata)
        self.report_progress(95)
        self.logger.info(f"Alpha158 metadata written path={self.context['metadata_path']}")

    def publish_output(self) -> None:
        self.context["metadata_file"] = str(self.context["metadata_path"])

    @staticmethod
    def _statistics(
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
