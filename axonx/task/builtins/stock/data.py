"""Stock artifact schemas and cutoff-safe, fixed-market-day targets."""

from collections.abc import Sequence
from typing import Any

import polars as pl

from ...contracts import BaseETLOutputParams


class StockETLOutput(BaseETLOutputParams):
    labels_file: str
    market_file: str
    calendar_file: str
    protocol: dict


VERSION = 2
KEYS = ("trade_date", "trade_time", "ts_code")
LABEL_COLUMNS = (
    *KEYS,
    "label_target_date",
    "label_return",
    "label_valid",
    "label_status",
)
MARKET_COLUMNS = (
    *KEYS,
    "price",
    "adjustment_factor",
    "can_buy",
    "can_sell",
    "market_status",
)
SIGNAL_COLUMNS = (
    *KEYS,
    "pred",
    "is_model_candidate",
    "is_buyable_at_signal",
    "signal_price",
    "signal_adjustment_factor",
)


def normalize_keys(frame: pl.DataFrame) -> pl.DataFrame:
    return frame.with_columns(pl.col("trade_date", "trade_time", "ts_code").cast(pl.String))


def validate_keys(frame: pl.DataFrame, columns: Sequence[str] = KEYS) -> None:
    if missing := set(columns) - set(frame.columns):
        raise ValueError(f"Missing stock keys: {sorted(missing)}")
    if (
        frame.select(columns).n_unique() != frame.height
        or frame.select(pl.any_horizontal(pl.col(columns).is_null()).any()).item()
    ):
        raise ValueError(f"Null or duplicate stock keys: {columns}")
    if (
        "trade_date" in columns
        and frame.select(
            (
                ~pl.col("trade_date").cast(pl.String).str.contains(r"^\d{8}$")
                | pl.col("trade_date").cast(pl.String).str.strptime(pl.Date, "%Y%m%d", strict=False).is_null()
            ).any()
        ).item()
    ):
        raise ValueError("trade_date must be YYYYMMDD")
    if (
        "trade_time" in columns
        and frame.select(
            (~pl.col("trade_time").cast(pl.String).str.contains(r"^(?:[01]\d|2[0-3])[0-5]\d$")).any()
        ).item()
    ):
        raise ValueError("trade_time must be HHMM")


def normalize_calendar(calendar: pl.DataFrame) -> pl.DataFrame:
    """Reject invalid calendar keys before they can change label or exit horizons."""
    validate_keys(calendar, ("trade_date",))
    if calendar.is_empty():
        raise ValueError("Empty market calendar")
    return calendar.select(pl.col("trade_date").cast(pl.String)).sort("trade_date")


def fixed_labels(signals: pl.DataFrame, market: pl.DataFrame, calendar: pl.DataFrame) -> pl.DataFrame:
    """Join the next MARKET date; never search ahead for a tradable stock quote."""
    signals, market = normalize_keys(signals), normalize_keys(market)
    validate_keys(signals)
    validate_keys(market)
    dates = normalize_calendar(calendar)
    if not set(signals["trade_date"]).issubset(dates["trade_date"]):
        raise ValueError("Signal dates must belong to the market calendar")
    dates = dates.with_columns(pl.col("trade_date").shift(-1).alias("label_target_date"))
    future = market.select(
        pl.col("trade_date").alias("label_target_date"),
        "trade_time",
        "ts_code",
        (pl.col("price") * pl.col("adjustment_factor")).alias("_target_price"),
        pl.col("market_status").alias("_target_status"),
    )
    result = signals.join(dates, on="trade_date", how="left", validate="m:1").join(
        future,
        on=["label_target_date", "trade_time", "ts_code"],
        how="left",
        validate="m:1",
    )
    result = result.join(
        market.select(*KEYS, pl.col("market_status").alias("_entry_status")), on=list(KEYS), how="left", validate="1:1"
    )
    last = market["trade_date"].max()
    valid = (
        (pl.col("_entry_status") == "quoted")
        & (pl.col("_target_status") == "quoted")
        & pl.col("_target_price").is_finite()
        & (pl.col("_target_price") > 0)
        & pl.col("signal_price").is_finite()
        & (pl.col("signal_price") > 0)
        & pl.col("signal_adjustment_factor").is_finite()
        & (pl.col("signal_adjustment_factor") > 0)
    ).fill_null(False)
    return (
        result.with_columns(
            valid.alias("label_valid"),
            pl.when(valid)
            .then(pl.col("_target_price") / (pl.col("signal_price") * pl.col("signal_adjustment_factor")) - 1)
            .alias("label_return"),
            pl.when(valid)
            .then(pl.lit("valid"))
            .when(pl.col("_entry_status").fill_null("missing_data") != "quoted")
            .then(pl.col("_entry_status").fill_null("missing_data"))
            .when(pl.col("label_target_date").is_null() | (pl.col("label_target_date") > last))
            .then(pl.lit("pending"))
            .otherwise(pl.col("_target_status").fill_null("missing_data"))
            .alias("label_status"),
        )
        .select(LABEL_COLUMNS)
        .sort(KEYS)
    )


def transform_labels(frame: pl.DataFrame, *, reference: pl.Expr, winsorize_tail: float) -> pl.DataFrame:
    """Only reference rows influence targets; retain other rows as sequence context."""
    if not 0 <= winsorize_tail < 0.5:
        raise ValueError("winsorize_tail must be in [0, .5)")
    keys = ["trade_date", "trade_time"]
    value = pl.when(reference & pl.col("label_valid") & pl.col("label_return").is_finite()).then(pl.col("label_return"))
    frame = frame.with_columns(value.alias("_target_raw"))
    v = pl.col("_target_raw")
    lower = v.quantile(winsorize_tail, interpolation="linear").over(keys)
    upper = v.quantile(1 - winsorize_tail, interpolation="linear").over(keys)
    frame = frame.with_columns(v.clip(lower, upper).alias("_target_clipped"))
    c = pl.col("_target_clipped")
    std, count = c.std(ddof=0).over(keys), v.count().over(keys)
    return frame.with_columns(
        pl.when(v.is_not_null())
        .then(pl.when(count > 1).then((v.rank(method="average").over(keys) - 1) / (count - 1)).otherwise(0.5))
        .alias("label_return_rank"),
        pl.when(v.is_not_null())
        .then(pl.when(std > 1e-12).then((c - c.mean().over(keys)) / std).otherwise(0.0))
        .alias("label_return_csz"),
    ).drop("_target_raw", "_target_clipped")


def stock_protocol(*, trade_time: str) -> dict[str, Any]:
    return {
        "version": VERSION,
        "trade_time": trade_time,
        "return_unit": "decimal",
        "date_format": "YYYYMMDD",
        "labels": "next market date at the same time; null when unavailable; no delayed exits",
        "label_transform": "training only, after cutoff and reference filtering",
        "market": "independent of feature eligibility; missing_data is never inferred as suspension",
    }


def apply_market_status(market: pl.DataFrame, status: pl.DataFrame | None) -> pl.DataFrame:
    """Merge independently confirmed suspension/missing states, including absent quote rows."""
    if status is None:
        return market
    market, status = normalize_keys(market), normalize_keys(status)
    validate_keys(status)
    if not set(status["market_status"]).issubset({"suspended", "missing_data"}):
        raise ValueError("Explicit market states must be suspended or missing_data")
    result = market.join(
        status.select(*KEYS, pl.col("market_status").alias("_status")),
        on=list(KEYS),
        how="full",
        coalesce=True,
    )
    result = result.with_columns(pl.coalesce("_status", "market_status").alias("market_status"))
    return (
        result.with_columns(
            (pl.col("can_buy").fill_null(False) & (pl.col("market_status") == "quoted")).alias("can_buy"),
            (pl.col("can_sell").fill_null(False) & (pl.col("market_status") == "quoted")).alias("can_sell"),
        )
        .drop("_status")
        .sort(KEYS)
    )
