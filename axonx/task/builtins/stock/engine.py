"""One mark-to-market cash/position ledger for stock prediction backtests."""

import math
from dataclasses import dataclass
from typing import Any, Protocol

import polars as pl

from .data import (
    KEYS,
    MARKET_COLUMNS,
    SIGNAL_COLUMNS,
    normalize_calendar,
    normalize_keys,
    validate_keys,
)

from .reporting import daily_output, summarize


class PortfolioPolicy(Protocol):
    """Plugin decision hook; the engine retains ownership of execution and cash."""

    def replacement_limit(self, n: int) -> int:
        """Maximum successful buys and sells per day, after initial construction."""

    def should_exit(self, *, rank: int | None, age: int, n: int) -> bool:
        """Decide using current candidate rank and elapsed market days only."""


@dataclass(frozen=True)
class BacktestConfig:
    top_ns: tuple[int, ...] = (1, 2, 3, 5, 10, 20, 30)
    holding_days: int | None = 1
    annual_risk_free_rate: float = 0.012
    annualization_days: int = 252
    minimum_index_weight_coverage: float = 0.98
    buy_cost_rate: float = 0.0005
    sell_cost_rate: float = 0.0015
    missing_market_as_suspension: bool = False


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
    buy_cost_rate, sell_cost_rate = config.buy_cost_rate, config.sell_cost_rate
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
    date_indices = {date: index for index, date in enumerate(all_dates)}
    if not (signal_dates := set(signals["trade_date"])).issubset(all_dates):
        raise ValueError("Signal dates must belong to the market calendar")
    dates = [d for d in all_dates if signals["trade_date"].min() <= d <= as_of_date]
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
    ranks_by_date = (
        {
            key[0]: dict(frame.select("ts_code", "target_rank").rows())
            for key, frame in targets.partition_by("trade_date", as_dict=True).items()
        }
        if policy is not None
        else {}
    )
    selected = targets.filter(pl.col("target_rank") <= max(config.top_ns))
    by_date = {key[0]: frame.to_dicts() for key, frame in selected.partition_by("trade_date", as_dict=True).items()}
    daily, orders, positions, trades = [], [], [], []
    incomplete = False
    successors = events.successors if events is not None else set()
    for n in config.top_ns:
        cash, previous_equity, book = 1.0, 1.0, {}
        if events is not None:
            events.reset(n)
        for date in dates:
            needed = {row["ts_code"] for row in by_date.get(date, [])[:n]} | set(book) | successors
            day_market = market_days.get(date)
            quotes = (
                {row["ts_code"]: row for row in day_market.filter(pl.col("ts_code").is_in(needed)).to_dicts()}
                if day_market is not None
                else {}
            )
            if events is not None:
                cash = events.apply(date, slot, book, cash, quotes)
            pending_cash = events.pending_cash if events is not None else 0.0
            if not math.isfinite(pending_cash) or pending_cash < 0:
                raise ValueError("Invalid pending cash")
            fees = bought = sold = 0.0
            sell_count = buy_count = 0
            limit = _replacement_limit(policy, n) if date != dates[0] else n
            ranks = ranks_by_date.get(date, {})
            delayed_exits = unfilled = 0
            held = (
                sorted(
                    book,
                    key=lambda code, current=ranks: (
                        -current.get(code, math.inf),
                        code,
                    ),
                )
                if policy is not None
                else list(book)
            )
            for code in held:
                position = book[code]
                quote = quotes.get(code)
                status = _quote_status(quote, config)
                if status == "quoted":
                    position["mark"] = quote["price"] * quote["adjustment_factor"]
                    if events is not None:
                        position["last_factor"] = quote["adjustment_factor"]
                elif status == "missing_data":
                    incomplete = True
                due = position["planned_exit_date"]
                eligible = (
                    date in signal_dates
                    and policy.should_exit(
                        rank=ranks.get(code),
                        age=date_indices[date] - date_indices[position["entry_date"]],
                        n=n,
                    )
                    if policy is not None
                    else due is not None and date >= due
                )
                if not eligible or sell_count >= limit:
                    continue
                if status != "quoted" or not quote["can_sell"]:
                    orders.append(
                        {
                            "top_n": n,
                            "trade_date": date,
                            "ts_code": code,
                            "side": "sell",
                            "status": "unfilled",
                            "reason": status if status != "quoted" else "not_sellable",
                            "notional": 0.0,
                            "fee": 0.0,
                        }
                    )
                    continue
                notional = position["units"] * position["mark"]
                fee = notional * sell_cost_rate
                cash += notional - fee
                sold += notional
                sell_count += 1
                fees += fee
                delayed_exits += due is not None and date > due
                orders.append(
                    {
                        "top_n": n,
                        "trade_date": date,
                        "ts_code": code,
                        "side": "sell",
                        "status": "filled",
                        "reason": "",
                        "notional": notional,
                        "fee": fee,
                    }
                )
                trades.append(
                    {
                        "top_n": n,
                        "ts_code": code,
                        "entry_date": position["entry_date"],
                        "exit_date": date,
                        "planned_exit_date": due,
                        "entry_price": position["entry_price"],
                        "exit_price": quote["price"],
                        "principal": position["principal"],
                        "realized_return": notional / position["principal"] - 1,
                        "fee": fee + position["entry_fee"],
                        "exit_delayed": due is not None and date > due,
                    }
                )
                del book[code]
            equity = cash + pending_cash + sum(p["units"] * p["mark"] for p in book.values())
            allocation = equity / n
            for signal in by_date.get(date, [])[:n]:
                code = signal["ts_code"]
                if code in book or buy_count >= limit:
                    continue
                quote = quotes.get(code)
                status = _quote_status(quote, config)
                blocked = events is not None and events.blocked(code)
                if status == "missing_data" and not blocked:
                    incomplete = True
                reason = (
                    "security_event"
                    if blocked
                    else (
                        status
                        if status != "quoted"
                        else ("not_buyable" if not quote["can_buy"] else "capacity" if len(book) >= n else "")
                    )
                )
                principal = min(allocation, cash / (1 + buy_cost_rate)) if not reason else 0.0
                if principal <= 1e-12:
                    unfilled += 1
                    orders.append(
                        {
                            "top_n": n,
                            "trade_date": date,
                            "ts_code": code,
                            "side": "buy",
                            "status": "unfilled",
                            "reason": reason or "cash",
                            "notional": 0.0,
                            "fee": 0.0,
                        }
                    )
                    continue
                index = date_indices[date] + config.holding_days if config.holding_days is not None else len(all_dates)
                due = all_dates[index] if index < len(all_dates) else None
                price = quote["price"] * quote["adjustment_factor"]
                fee = principal * buy_cost_rate
                book[code] = {
                    "units": principal / price,
                    "mark": price,
                    "principal": principal,
                    "entry_price": quote["price"],
                    "entry_fee": fee,
                    "entry_date": date,
                    "planned_exit_date": due,
                }
                if events is not None:
                    book[code].update(
                        entry_shares=principal / quote["price"],
                        entry_factor=quote["adjustment_factor"],
                        last_factor=quote["adjustment_factor"],
                    )
                cash -= principal + fee
                fees += fee
                bought += principal
                buy_count += 1
                orders.append(
                    {
                        "top_n": n,
                        "trade_date": date,
                        "ts_code": code,
                        "side": "buy",
                        "status": "filled",
                        "reason": "",
                        "notional": principal,
                        "fee": fee,
                    }
                )
            equity = cash + pending_cash + sum(p["units"] * p["mark"] for p in book.values())
            if not math.isfinite(cash) or not math.isfinite(equity) or cash < -1e-10 or equity <= 0:
                raise ValueError("Invalid portfolio cash or equity")
            for code, p in book.items():
                due = p["planned_exit_date"]
                positions.append(
                    {
                        "top_n": n,
                        "trade_date": date,
                        "ts_code": code,
                        "entry_date": p["entry_date"],
                        "planned_exit_date": due,
                        "market_value": p["units"] * p["mark"],
                        "weight": p["units"] * p["mark"] / equity,
                        "units": p["units"],
                        "exit_delayed": due is not None and date >= due,
                    }
                )
            daily.append(
                {
                    "top_n": n,
                    "trade_date": date,
                    "net_value": equity,
                    "net_return": equity / previous_equity - 1,
                    "gross_return": (equity + fees) / previous_equity - 1,
                    "transaction_cost": fees / previous_equity,
                    "turnover": (bought + sold) / previous_equity,
                    "cash": cash,
                    "cash_weight": cash / equity,
                    "count": len(book),
                    "open_positions": len(book),
                    "delayed_open_positions": sum(
                        p["planned_exit_date"] is not None and date >= p["planned_exit_date"] for p in book.values()
                    ),
                    "unsettled_positions": len(book),
                    "delayed_exits": delayed_exits,
                    "unfilled_entries": unfilled,
                }
            )
            if events is not None:
                daily[-1]["pending_cash"] = pending_cash
            previous_equity = equity
    # Keep exported records chronological across independent Top N runs.
    n_order = {n: index for index, n in enumerate(config.top_ns)}
    for rows in (orders, positions, trades):
        rows.sort(
            key=lambda row: (
                row.get("trade_date", row.get("exit_date")),
                n_order[row["top_n"]],
            )
        )
    output, targets, benchmarks = daily_output(dates, daily, signals, targets, labels, as_of_date, config)
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
        "orders": _frame(
            orders,
            {
                "top_n": pl.Int64,
                "trade_date": pl.String,
                "ts_code": pl.String,
                "side": pl.String,
                "status": pl.String,
                "reason": pl.String,
                "notional": pl.Float64,
                "fee": pl.Float64,
            },
        ),
        "positions": _frame(
            positions,
            {
                "top_n": pl.Int64,
                "trade_date": pl.String,
                "ts_code": pl.String,
                "entry_date": pl.String,
                "planned_exit_date": pl.String,
                "market_value": pl.Float64,
                "weight": pl.Float64,
                "units": pl.Float64,
                "exit_delayed": pl.Boolean,
            },
        ),
        "trades": _frame(
            trades,
            {
                "top_n": pl.Int64,
                "ts_code": pl.String,
                "entry_date": pl.String,
                "exit_date": pl.String,
                "planned_exit_date": pl.String,
                "entry_price": pl.Float64,
                "exit_price": pl.Float64,
                "principal": pl.Float64,
                "realized_return": pl.Float64,
                "fee": pl.Float64,
                "exit_delayed": pl.Boolean,
            },
        ),
    }
    return BacktestResult(frames, benchmarks, "incomplete_market_data" if incomplete else "done")


def _replacement_limit(policy: PortfolioPolicy | None, n: int) -> int:
    limit = policy.replacement_limit(n) if policy is not None else n
    if not 1 <= limit <= n:
        raise ValueError("Portfolio policy replacement limit must be between 1 and N")
    return limit


def _quote_status(quote: dict[str, Any] | None, config: BacktestConfig) -> str:
    status = quote["market_status"] if quote else "missing_data"
    if status == "missing_data" and config.missing_market_as_suspension:
        # TODO: Use independently sourced suspension intervals to distinguish
        # actual suspensions from missing quotes; this is a temporary assumption.
        return "suspended"
    return status


def _frame(rows: list[dict[str, Any]], schema: dict[str, Any]) -> pl.DataFrame:
    return pl.DataFrame(rows, schema=schema)


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
