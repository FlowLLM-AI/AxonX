"""Data preparation and market calculations for Alpha158 ETL."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import polars as pl

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
LABELS = ("label_1d",)
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
    "entry_is_buyable",
    "exit_is_sellable",
    "entry_date",
    "exit_date",
    "exit_delayed",
)


def load_market_data(daily_files: list[Path], factor_files: list[Path]) -> pl.DataFrame:
    """Join daily quotes and adjustment factors in symbol and date order."""
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
        pl.scan_parquet(daily_files)
        .select(
            pl.col("ts_code").cast(pl.String),
            pl.col("trade_date").cast(pl.String),
            *(pl.col(column).cast(pl.Float64) for column in daily_columns[2:]),
        )
        .filter(~pl.col("ts_code").str.ends_with(".BJ"))
    )
    factors = (
        pl.scan_parquet(factor_files)
        .select(
            pl.col("ts_code").cast(pl.String),
            pl.col("trade_date").cast(pl.String),
            pl.col("adj_factor").cast(pl.Float64),
        )
        .filter(~pl.col("ts_code").str.ends_with(".BJ"))
    )
    return daily.join(factors, on=["ts_code", "trade_date"], how="left").collect().sort("ts_code", "trade_date")


def validate_market_data(frame: pl.DataFrame) -> None:
    """Reject invalid quote dates and missing or out-of-range numeric values."""
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
    if frame.select("ts_code", "trade_date").n_unique() != frame.height:
        raise ValueError("输入包含重复的 ts_code, trade_date")


def align_calendar(frame: pl.DataFrame, calendar: pl.DataFrame) -> pl.DataFrame:
    """Limit the market calendar to quote dates and reject non-trading dates."""
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
    return calendar


def infer_lifecycle_bounds(
    frame: pl.DataFrame,
    stocks: pl.DataFrame,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Infer panel bounds for quotes missing from stock_basic."""
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
    bounds = bounds.with_columns(
        pl.coalesce("name", "ts_code").alias("name"),
        pl.coalesce("list_date", "_first_trade_date").alias("list_date"),
        pl.when(~pl.col("_has_stock_basic"))
        .then(pl.col("_last_trade_date"))
        .otherwise(pl.col("delist_date"))
        .alias("_panel_end_date"),
    ).drop("_first_trade_date", "_last_trade_date", "_has_stock_basic")
    return bounds, missing_stock_basic


def assemble_trading_panel(
    frame: pl.DataFrame,
    bounds: pl.DataFrame,
    calendar: pl.DataFrame,
) -> pl.DataFrame:
    """Expand lifecycle bounds over trading days and derive adjusted inputs."""
    return (
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


def load_price_limits(paths: list[Path]) -> pl.DataFrame:
    """Read official price limits, or return the same empty schema when absent."""
    return (
        pl.scan_parquet(paths)
        .select(
            pl.col("ts_code").cast(pl.String),
            pl.col("trade_date").cast(pl.String),
            pl.col("up_limit", "down_limit").cast(pl.Float64),
        )
        .collect()
        if paths
        else pl.DataFrame(
            schema={
                "ts_code": pl.String,
                "trade_date": pl.String,
                "up_limit": pl.Float64,
                "down_limit": pl.Float64,
            },
        )
    )


def join_historical_names_and_limits(
    frame: pl.DataFrame,
    names: pl.DataFrame,
    limits: pl.DataFrame,
) -> pl.DataFrame:
    """Match the last known name and official limits to each trading day."""
    if limits.select("ts_code", "trade_date").n_unique() != limits.height:
        raise ValueError("stk_limit 包含重复的 ts_code, trade_date")
    historical_names = names.rename({"name": "_historical_name"})
    return (
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


def apply_price_limits(frame: pl.DataFrame, st_limit_change_date: str) -> pl.DataFrame:
    """Use official limits when valid and otherwise calculate board-specific limits."""
    official_limits_valid = (
        pl.col("up_limit").is_finite() & pl.col("down_limit").is_finite() & (pl.col("up_limit") > pl.col("down_limit"))
    ).fill_null(False)
    is_st_name = pl.col("name").str.to_uppercase().str.contains("ST")
    is_growth_board = (
        pl.col("ts_code").str.starts_with("300")
        | pl.col("ts_code").str.starts_with("301")
        | pl.col("ts_code").str.starts_with("688")
        | pl.col("ts_code").str.starts_with("689")
    )
    limit_rate = (
        pl.when(is_st_name & (pl.col("trade_date") < st_limit_change_date))
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
    return frame.with_columns(
        (~official_limits_valid & pl.col("_has_market_data")).alias(
            "_used_limit_fallback",
        ),
        pl.when(official_limits_valid).then(pl.col("up_limit")).otherwise(fallback_up).alias("up_limit"),
        pl.when(official_limits_valid).then(pl.col("down_limit")).otherwise(fallback_down).alias("down_limit"),
    )


def attach_market_flags(
    frame: pl.DataFrame,
    history_days: int,
    min_history_coverage: float,
) -> pl.DataFrame:
    """Calculate market state and buyability from adjusted trading-panel rows."""
    observed = (
        pl.col("_has_market_data").cast(pl.Int16).rolling_sum(window_size=history_days, min_samples=1).over("ts_code")
    )
    history_span = pl.col("_trade_index") - pl.col("_trade_index").min().over("ts_code") + 1
    valid_limits = (
        pl.col("up_limit").is_finite() & pl.col("down_limit").is_finite() & (pl.col("up_limit") > pl.col("down_limit"))
    )
    upper_name = pl.col("name").str.to_uppercase()
    return frame.with_columns(
        upper_name.str.contains(r"^(?:S\*?ST|\*ST|ST)").alias("is_st"),
        pl.col("name").str.contains(r"^退|退$").alias("is_delisting"),
        (valid_limits & (pl.col("close") >= pl.col("up_limit") - 1e-6)).alias(
            "is_limit_up",
        ),
        (valid_limits & (pl.col("close") <= pl.col("down_limit") + 1e-6)).alias(
            "is_limit_down",
        ),
        ((history_span < history_days) | (observed / history_days < min_history_coverage)).alias(
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


def calculate_labels(
    frame: pl.DataFrame,
    winsorize_tail: float,
    *,
    progress: Callable[[float], None] | None = None,
) -> pl.DataFrame:
    """Build returns through the first sellable open on or after the planned exit."""
    sellable = (
        pl.col("_has_market_data")
        & pl.col("_has_valid_limits")
        & (pl.col("open") > pl.col("down_limit") + 1e-6)
    ).fill_null(False)
    frame = frame.with_columns(
        pl.when(sellable).then(pl.col("_open")).alias("_sellable_open"),
        pl.when(sellable).then(pl.col("trade_date")).alias("_sellable_date"),
    ).with_columns(
        pl.col("_sellable_open").backward_fill().over("ts_code").alias("_next_sellable_open"),
        pl.col("_sellable_date").backward_fill().over("ts_code").alias("_next_sellable_date"),
    )
    frame = frame.with_columns(
        (pl.col("_next_sellable_open").shift(-2).over("ts_code") / pl.col("_open").shift(-1).over("ts_code") - 1).alias("label_1d"),
        pl.col("trade_date").shift(-1).over("ts_code").alias("entry_date"),
        pl.col("_next_sellable_date").shift(-2).over("ts_code").alias("exit_date"),
        pl.col("trade_date").shift(-2).over("ts_code").alias("_planned_exit_date"),
        (
            pl.col("_has_market_data").shift(-1).over("ts_code").fill_null(False)
            & pl.col("_has_valid_limits").shift(-1).over("ts_code").fill_null(False)
            & ~pl.col("is_st").shift(-1).over("ts_code").fill_null(True)
            & ~pl.col("is_delisting").shift(-1).over("ts_code").fill_null(True)
            & (
                pl.col("open").shift(-1).over("ts_code")
                < pl.col("up_limit").shift(-1).over("ts_code") - 1e-6
            ).fill_null(False)
        ).alias("entry_is_buyable"),
        sellable.shift(-2).over("ts_code").fill_null(False).alias("exit_is_sellable"),
    )
    frame = frame.with_columns(
        pl.col("label_1d").is_finite().fill_null(False).alias("label_1d_is_valid"),
        (pl.col("exit_date") != pl.col("_planned_exit_date"))
        .fill_null(pl.col("_planned_exit_date").is_not_null())
        .alias("exit_delayed"),
    )
    if progress is not None:
        progress(30)
    finite = pl.when(pl.col("label_1d_is_valid") & ~pl.col("exit_delayed")).then(pl.col("label_1d"))
    lower = finite.quantile(winsorize_tail, interpolation="linear").over("trade_date")
    upper = finite.quantile(1 - winsorize_tail, interpolation="linear").over("trade_date")
    frame = frame.with_columns(finite.clip(lower, upper).alias("_label_1d_winsorized"))
    if progress is not None:
        progress(60)
    winsorized = pl.col("_label_1d_winsorized")
    mean = winsorized.mean().over("trade_date")
    std = winsorized.std(ddof=0).over("trade_date")
    count = finite.count().over("trade_date")
    frame = frame.with_columns(
        pl.when(std > EPSILON).then((winsorized - mean) / std).alias("label_1d_csz"),
        pl.when(pl.col("label_1d_is_valid") & ~pl.col("exit_delayed") & (count > 0))
        .then(finite.rank(method="average").over("trade_date") / count)
        .alias("label_1d_rank"),
    ).drop("_label_1d_winsorized", "_sellable_open", "_sellable_date", "_next_sellable_open", "_next_sellable_date", "_planned_exit_date")
    if progress is not None:
        progress(95)
    return frame


def load_index_weights(paths: list[Path]) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Load HS300 snapshots and reject duplicate symbol/date weights."""
    weights = (
        pl.scan_parquet(paths)
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
    return weights, weights.select("_weight_date").unique().sort("_weight_date")


def join_index_weights(frame: pl.DataFrame, weights: pl.DataFrame, snapshots: pl.DataFrame) -> pl.DataFrame:
    """Attach the most recent HS300 weight snapshot for each trading date."""
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
