"""One mark-to-market cash/position ledger for stock prediction backtests."""

from dataclasses import dataclass

import polars as pl

from .data import (
    KEYS,
    MARKET_COLUMNS,
    SIGNAL_COLUMNS,
    normalize_calendar,
    normalize_keys,
    validate_keys,
)
from .ledger import PortfolioLedger, PortfolioPolicy
from .models import BacktestConfig
from .reporting import daily_output, summarize


@dataclass
class BacktestResult:
    frames: dict[str, pl.DataFrame]
    benchmark_keys: tuple[str, ...]
    status: str


def _validate_config(config: BacktestConfig, policy: PortfolioPolicy | None) -> None:
    if not config.top_ns or any(n < 1 for n in config.top_ns):
        raise ValueError("Positive top_ns are required")
    if policy is None and (config.holding_days is None or config.holding_days < 1):
        raise ValueError("Fixed-expiry backtests require positive holding_days")
    if policy is not None and config.holding_days is not None:
        raise ValueError("Portfolio policies require holding_days=None")
    if not 0 <= config.buy_cost_rate < 1 or not 0 <= config.sell_cost_rate < 1:
        raise ValueError("buy_cost_rate and sell_cost_rate must be in [0,1)")


def run_backtest(
    signals: pl.DataFrame,
    market: pl.DataFrame,
    calendar: pl.DataFrame,
    labels: pl.DataFrame | None,
    config: BacktestConfig,
    *,
    as_of_date: str,
    policy: PortfolioPolicy | None = None,
    universe_keys: pl.DataFrame | None = None,
    events=None,
) -> BacktestResult:
    """Replay each Top N independently; optional events supply reset/apply/blocked hooks."""
    _validate_config(config, policy)
    signals, market = normalize_keys(signals), normalize_keys(market)
    for frame, required in ((signals, SIGNAL_COLUMNS), (market, MARKET_COLUMNS)):
        if missing := set(required) - set(frame.columns):
            raise ValueError(f"Missing stock artifact columns: {sorted(missing)}")
        validate_keys(frame)
    if signals.is_empty():
        raise ValueError("No recorded signals")
    for frame, columns in (
        (signals, ["pred", "signal_price", "signal_adjustment_factor"]),
        (
            market.filter(pl.col("market_status") == "quoted"),
            ["price", "adjustment_factor"],
        ),
    ):
        if frame.select(
            pl.any_horizontal(*(pl.col(c).is_null() | ~pl.col(c).is_finite() for c in columns)).any()
        ).item():
            raise ValueError("Non-finite stock artifact values")
    if (
        market.filter(pl.col("market_status") == "quoted")
        .filter((pl.col("price") <= 0) | (pl.col("adjustment_factor") <= 0))
        .height
    ):
        raise ValueError("Quoted prices and factors must be positive")
    if not set(market["market_status"]).issubset({"quoted", "suspended", "missing_data"}):
        raise ValueError("Unknown market_status")
    for frame, cols in (
        (signals, ["is_model_candidate", "is_buyable_at_signal"]),
        (market, ["can_buy", "can_sell"]),
    ):
        if any(frame.schema[c] != pl.Boolean or frame[c].null_count() for c in cols):
            raise ValueError("Stock state flags must be non-null Boolean")
    if signals["trade_time"].n_unique() != 1:
        raise ValueError("Each backtest runs one signal time")
    slot = signals["trade_time"][0]
    market = market.filter(pl.col("trade_time") == slot)
    all_dates = normalize_calendar(calendar)["trade_date"].to_list()
    if not (signal_dates := set(signals["trade_date"])).issubset(all_dates):
        raise ValueError("Signal dates must belong to the market calendar")
    first_date = signals["trade_date"].min()
    dates = [date for date in all_dates if first_date <= date <= as_of_date]
    if not dates:
        raise ValueError("No calendar dates within evaluation cutoff")
    targets = _candidates(
        signals.filter(pl.col("trade_date") <= as_of_date), _validate_universe_keys(signals, universe_keys)
    )
    market_days = {
        key[0]: frame
        for key, frame in market.filter(pl.col("trade_date").is_between(pl.lit(dates[0]), pl.lit(dates[-1])))
        .partition_by("trade_date", as_dict=True)
        .items()
    }
    candidate_days = targets.partition_by("trade_date", as_dict=True)
    ranks_by_date = (
        {key[0]: dict(frame.select("ts_code", "target_rank").rows()) for key, frame in candidate_days.items()}
        if policy is not None
        else {}
    )
    maximum_n = max(config.top_ns)
    by_date = {key[0]: frame.head(maximum_n).to_dicts() for key, frame in candidate_days.items()}
    ledger = PortfolioLedger(config, all_dates, slot, policy=policy, events=events)
    for n in config.top_ns:
        ledger.replay(n, dates, market_days, by_date, ranks_by_date, signal_dates)
    output, targets, benchmarks = daily_output(dates, ledger.daily, signals, targets, labels, as_of_date, config)
    frames = {
        "daily": output,
        "summary": summarize(
            output,
            benchmarks,
            config.annual_risk_free_rate,
            config.annualization_days,
            config.top_ns,
        ),
        "signals": signals.join(
            targets.select(
                *KEYS,
                pl.lit(True).alias("is_backtest_candidate"),
                "target_rank",
                pl.col("_target_return").alias("label_return"),
            ),
            on=list(KEYS),
            how="left",
            validate="1:1",
            maintain_order="left",
        ).with_columns(pl.col("is_backtest_candidate").fill_null(False)),
        **ledger.frames(),
    }
    return BacktestResult(frames, benchmarks, "incomplete_market_data" if ledger.incomplete else "done")


def _validate_universe_keys(signals, universe_keys):
    if universe_keys is None:
        return None
    keys = normalize_keys(universe_keys.select(*KEYS))
    validate_keys(keys)
    if keys.join(signals.select(*KEYS), on=list(KEYS), how="anti").height:
        raise ValueError("Universe keys must be a subset of prediction keys")
    return keys


def _candidates(signals: pl.DataFrame, universe_keys: pl.DataFrame | None) -> pl.DataFrame:
    candidates = signals.filter(pl.col("is_model_candidate") & pl.col("is_buyable_at_signal"))
    if universe_keys is not None:
        candidates = candidates.join(universe_keys, on=list(KEYS), how="semi")
    return candidates.sort(["trade_date", "pred", "ts_code"], descending=[False, True, False]).with_columns(
        pl.int_range(1, pl.len() + 1).over("trade_date").alias("target_rank")
    )
