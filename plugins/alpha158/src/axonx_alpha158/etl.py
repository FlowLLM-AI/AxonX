"""Build a compact Alpha158 dataset from DownloadTushareTask output."""

from __future__ import annotations
import os
from collections.abc import Callable, Iterable
from pathlib import Path

import polars as pl
from pydantic import Field, field_validator
from pydantic.json_schema import SkipJsonSchema

from axonx.task.artifacts import artifact_record
from axonx.task.base import TaskStep
from axonx.task.core import BaseETLInputParams, BaseETLOutputParams, BaseETLTask

from .internal import etl_pipeline
from .internal.etl_pipeline import (
    CSZ_LABELS,
    FEATURES,
    HISTORY_DAYS,
    KBAR,
    LABEL_OUTPUTS,
    LABELS,
    MARKET_STATE_COLUMNS,
    PRICE,
    RANK_LABELS,
    RAW_FEATURES,
    ROLLING,
    ST_LIMIT_CHANGE_DATE,
    VALID_LABELS,
    WINDOWS,
    align_calendar,
    apply_price_limits,
    assemble_trading_panel,
    attach_market_flags,
    calculate_labels,
    fill_missing_adj_factors,
    infer_lifecycle_bounds,
    join_historical_names_and_limits,
    join_index_weights,
    load_index_weights,
    load_market_data,
    load_price_limits,
    validate_market_data,
)
from .internal.features import (
    all_features,
    dataset_statistics,
    price_features,
    rolling_features,
    rolling_inputs,
)

EPSILON = etl_pipeline.EPSILON


class Alpha158OutputParams(BaseETLOutputParams):
    statistics_file: str
    feature_count: int
    symbols: int
    feature_schema: dict
    labels: dict
    index_weight_columns: list[str]
    market_state_columns: list[str]
    market_state: dict
    column_schema: dict[str, str] = Field(alias="schema")


class Alpha158InputParams(BaseETLInputParams):
    """Configure source data and the dates included in the Alpha158 dataset."""

    input_dir: SkipJsonSchema[Path] = Path("tushare")
    start_date: str | None = Field(default="20140101", description="First output trading date in YYYYMMDD format; set null for all available dates.")
    end_date: str | None = Field(default=None, description="Last output trading date in YYYYMMDD format; defaults to the latest available date.")
    csz_winsorize_tail: float = Field(
        default=0.025,
        ge=0.0,
        lt=0.5,
        description="Fraction clipped from each daily return tail before label z-scoring.",
    )
    min_history_coverage: float = Field(default=0.8, gt=0.0, le=1.0, description="Minimum observed price history required for rolling features.")

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def normalize_date(cls, value: object) -> object:
        """Accept integer dates from YAML while preserving other inputs."""
        return str(value) if isinstance(value, int) and not isinstance(value, bool) else value


class Alpha158Task(BaseETLTask):
    """Build an Alpha158 dataset from downloaded Tushare market data.

    Produces adjusted features, one- to five-day future return labels, market
    status, and HS300 weights for training and analysis.
    """

    input_cls = Alpha158InputParams
    output_cls = Alpha158OutputParams
    input_params: Alpha158InputParams

    _price_features = staticmethod(price_features)
    _rolling_inputs = staticmethod(rolling_inputs)
    _features = staticmethod(all_features)
    _rolling = staticmethod(rolling_features)
    _statistics = staticmethod(dataset_statistics)

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

    def resolve_paths(self) -> None:
        """Resolve source partitions and output paths for this task."""
        input_dir = self.resolve_workspace_path(self.input_params.input_dir)
        daily_files = sorted(input_dir.glob("*/*/daily.parquet"))
        factor_files = sorted(input_dir.glob("*/*/adj_factor.parquet"))
        weight_files = sorted(input_dir.glob("*/*/index_weight.parquet"))
        static_files = {name: input_dir / f"{name}.parquet" for name in ("trade_cal", "stock_basic", "namechange")}
        if not daily_files or not factor_files:
            raise FileNotFoundError(f"缺少 daily 或 adj_factor 分区: {input_dir}")
        missing = [path for path in static_files.values() if not path.is_file()]
        if missing:
            raise FileNotFoundError(
                f"缺少 Alpha158 主数据: {', '.join(map(str, missing))}",
            )
        if self.input_params.start_date and self.input_params.end_date and self.input_params.start_date > self.input_params.end_date:
            raise ValueError("start_date 不能晚于 end_date")
        output_path = self.task_dir / "alpha158.parquet"
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
        )
        self.logger.info(
            f"Alpha158 paths resolved input_dir={input_dir} "
            f"daily_files={len(daily_files)} factor_files={len(factor_files)} "
            f"weight_files={len(weight_files)} output_file={output_path}",
        )

    def load_and_validate_market_data(self) -> None:
        """Load the quote and adjustment-factor partitions and validate their rows."""
        frame = load_market_data(
            self.context["daily_files"],
            self.context["factor_files"],
        )
        self.report_progress(70)
        frame, missing_rows, unresolved_rows = fill_missing_adj_factors(frame)
        self.context["filled_adj_factor_rows"] = missing_rows - unresolved_rows
        self.logger.info(
            f"Adjustment factors checked missing_rows={missing_rows} "
            f"filled_rows={self.context['filled_adj_factor_rows']} "
            f"unresolved_rows={unresolved_rows}",
        )
        self.report_progress(80)
        validate_market_data(frame)
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
            pl.read_parquet(
                self.context["trade_cal_file"],
                columns=("cal_date", "is_open"),
            )
            .with_columns(
                pl.col("cal_date").cast(pl.String),
                pl.col("is_open").cast(pl.Int8),
            )
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
            .with_columns(
                pl.col("ts_code", "name", "list_date", "delist_date").cast(pl.String),
            )
            .with_columns(
                pl.when(pl.col("delist_date") == "").then(None).otherwise(pl.col("delist_date")).alias("delist_date"),
            )
        )
        names = (
            pl.read_parquet(
                self.context["namechange_file"],
                columns=("ts_code", "name", "start_date", "ann_date"),
            )
            .with_columns(
                pl.col("ts_code", "name", "start_date", "ann_date").cast(pl.String),
            )
            .with_columns(
                pl.max_horizontal("start_date", "ann_date").alias("_known_date"),
            )
            .sort("ts_code", "_known_date", "start_date")
            .unique(("ts_code", "_known_date"), keep="last")
            .sort("ts_code", "_known_date")
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
        calendar = align_calendar(frame, calendar)
        bounds, missing_stock_basic = infer_lifecycle_bounds(frame, stocks)
        self.context["missing_stock_basic_symbols"] = missing_stock_basic.height
        if not missing_stock_basic.is_empty():
            sample = missing_stock_basic["ts_code"].head(10).to_list()
            self.logger.warning(
                "daily contains symbols absent from stock_basic; inferring lifecycle "
                f"from quote bounds symbols={missing_stock_basic.height} sample={sample}",
            )
        self.report_progress(20)
        frame = assemble_trading_panel(frame, bounds, calendar)
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
        limits = load_price_limits(self.context["limit_files"])
        self.report_progress(20)
        frame = join_historical_names_and_limits(frame, names, limits)
        self.report_progress(45)
        frame = apply_price_limits(frame, ST_LIMIT_CHANGE_DATE)
        self.report_progress(65)
        frame = attach_market_flags(
            frame,
            HISTORY_DAYS,
            self.input_params.min_history_coverage,
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
        self.logger.info(
            f"Base features calculated rows={frame.height} features={len(KBAR) + len(PRICE)}",
        )

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
            self.logger.info(
                f"Rolling features calculated window={window} progress={percentage}%",
            )
        rolling_columns = [column for rolling_frame in rolling_frames for column in rolling_frame.get_columns()]
        self.context["frame"] = frame.hstack(rolling_columns)

    def calculate_labels(self) -> None:
        """Calculate forward returns and their cross-sectional transformations."""
        self.logger.info(
            f"Calculating labels horizons={len(LABELS)} " f"winsorize_tail={self.input_params.csz_winsorize_tail}",
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
        self.logger.info(
            f"HS300 weights attached files={len(self.context['weight_files'])}",
        )

    def finalize_dataset(self) -> None:
        """Apply the requested date range and project the public output schema."""
        frame: pl.DataFrame = self.context["frame"]

        if self.input_params.start_date:
            frame = frame.filter(pl.col("trade_date") >= self.input_params.start_date)
        if self.input_params.end_date:
            frame = frame.filter(pl.col("trade_date") <= self.input_params.end_date)
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
            f"start_date={self.input_params.start_date or '-'} "
            f"end_date={self.input_params.end_date or '-'}",
        )

    def calculate_statistics(self) -> None:
        """Calculate data-quality statistics with bounded progress updates."""
        self.context["statistics"] = self._statistics(
            self.context["output"],
            progress=self.report_progress,
        )
        self.logger.info(
            f"Data-quality statistics calculated " f"columns={self.context['statistics'].height}",
        )

    def _labels(
        self,
        frame: pl.DataFrame,
        *,
        progress: Callable[[float], None] | None = None,
    ) -> pl.DataFrame:
        """Keep the existing Task helper while delegating label calculations."""
        return calculate_labels(
            frame,
            self.input_params.csz_winsorize_tail,
            progress=progress,
        )

    def _weights(self, frame: pl.DataFrame) -> pl.DataFrame:
        """Attach index snapshots while keeping Task logging at the boundary."""
        paths = self.context["weight_files"]
        if not paths:
            self.logger.warning("No HS300 weight files found; index weights will be null")
            return frame.with_columns(pl.lit(None, dtype=pl.Float64).alias("index_weight_hs300"))
        weights, snapshots = load_index_weights(paths)
        self.logger.info(f"HS300 weight snapshots loaded rows={weights.height} snapshots={snapshots.height}")
        return join_index_weights(frame, weights, snapshots)

    def write_outputs(self) -> None:
        """Write the dataset and statistics files before publishing metadata."""
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

    def build_output_params(self) -> Alpha158OutputParams:
        """Publish the dataset contract used by every downstream Alpha158 task."""
        output: pl.DataFrame = self.context["output"]
        task_dir: Path = self.task_dir
        dataset_record = artifact_record(self.context["output_path"], task_dir)
        statistics_record = artifact_record(self.context["statistics_path"], task_dir)
        return self.output_cls(
            date_range={
                "start": output["trade_date"].min(),
                "end": output["trade_date"].max(),
            },
            rows=output.height,
            symbols=output["ts_code"].n_unique(),
            feature_columns=list(FEATURES),
            label_columns=list(LABEL_OUTPUTS),
            feature_schema={
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
                            "features": [f"f_alpha158_{family}{window}" for window in WINDOWS],
                        }
                        for family in ROLLING
                    ],
                ],
            },
            labels={
                "raw": list(LABELS),
                "csz": list(CSZ_LABELS),
                "rank": list(RANK_LABELS),
                "valid": list(VALID_LABELS),
                "return_unit": "decimal",
                "definition": "adjusted close return from trade_date to the Nth following market trading day",
            },
            index_weight_columns=["index_weight_hs300"],
            market_state_columns=list(MARKET_STATE_COLUMNS),
            market_state={
                "buyable_definition": (
                    "listed, quoted, valid limits, non-ST, non-delisting, non-limit, sufficient history"
                ),
                "minimum_history_days": HISTORY_DAYS,
                "minimum_history_coverage": self.input_params.min_history_coverage,
                "missing_stock_basic_symbols": self.context["missing_stock_basic_symbols"],
                "missing_stock_basic_policy": (
                    "name=ts_code, list_date=first_quote, panel_end=last_quote, delist_date=null"
                ),
                "fallback_limit_rows": self.context["fallback_limit_rows"],
                "missing_limit_rows": self.context["missing_limit_rows"],
            },
            schema={name: str(dtype) for name, dtype in output.schema.items()},
            artifacts={
                "dataset": dataset_record,
                "statistics": statistics_record,
            },
            output_file=self.context["output_file"],
            statistics_file=self.context["statistics_file"],
            feature_count=self.context["feature_count"],
        )
