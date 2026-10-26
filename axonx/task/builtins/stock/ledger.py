"""Cash, positions and execution records for independent Top N portfolios."""

import math
from typing import Any, Protocol

import polars as pl

from .models import BacktestConfig


class PortfolioPolicy(Protocol):
    """Plugins decide exits; the ledger owns execution, cash and positions."""

    def replacement_limit(self, n: int) -> int:
        """Maximum successful buys and sells per day after initial construction."""

    def should_exit(self, *, rank: int | None, age: int, n: int) -> bool:
        """Decide using current candidate rank and elapsed market days only."""


class PortfolioLedger:
    """Replay independent portfolios into one collection of execution records."""

    def __init__(
        self,
        config: BacktestConfig,
        calendar: list[str],
        trade_time: str,
        *,
        policy: PortfolioPolicy | None = None,
        events=None,
    ):
        self.config = config
        self.calendar = calendar
        self.date_indices = {date: index for index, date in enumerate(calendar)}
        self.trade_time = trade_time
        self.policy = policy
        self.events = events
        self.daily: list[dict[str, Any]] = []
        self.orders: list[dict[str, Any]] = []
        self.positions: list[dict[str, Any]] = []
        self.trades: list[dict[str, Any]] = []
        self.incomplete = False
        self.n = 0
        self.cash = self.previous_equity = 1.0
        self.book: dict[str, dict[str, Any]] = {}

    def replay(self, n, dates, market_days, signals_by_date, ranks_by_date, signal_dates) -> None:
        """Reset portfolio and event state while retaining records from earlier runs."""
        self.n = n
        self.cash = self.previous_equity = 1.0
        self.book = {}
        if self.events is not None:
            self.events.reset(n)
        successors = self.events.successors if self.events is not None else set()
        for date in dates:
            signals = signals_by_date.get(date, [])[:n]
            needed = {row["ts_code"] for row in signals} | self.book.keys() | successors
            day_market = market_days.get(date)
            quotes = (
                {row["ts_code"]: row for row in day_market.filter(pl.col("ts_code").is_in(needed)).to_dicts()}
                if day_market is not None
                else {}
            )
            self._advance(
                date,
                quotes,
                signals,
                ranks_by_date.get(date, {}),
                initial=date == dates[0],
                signal_date=date in signal_dates,
            )

    def _advance(self, date, quotes, signals, ranks, *, initial, signal_date) -> None:
        if self.events is not None:
            self.cash = self.events.apply(date, self.trade_time, self.book, self.cash, quotes)
        pending_cash = self.events.pending_cash if self.events is not None else 0.0
        if not math.isfinite(pending_cash) or pending_cash < 0:
            raise ValueError("Invalid pending cash")

        limit = self.n if initial else self._replacement_limit()
        sell_fees, sold, delayed_exits = self._sell(date, quotes, ranks, limit, signal_date)
        allocation = self._equity(pending_cash) / self.n
        buy_fees, bought, unfilled = self._buy(date, quotes, signals, limit, allocation)
        fees = sell_fees + buy_fees
        equity = self._equity(pending_cash)
        if not math.isfinite(self.cash) or not math.isfinite(equity) or self.cash < -1e-10 or equity <= 0:
            raise ValueError("Invalid portfolio cash or equity")
        for code, position in self.book.items():
            due = position["planned_exit_date"]
            value = position["units"] * position["mark"]
            self.positions.append(
                {
                    "top_n": self.n,
                    "trade_date": date,
                    "ts_code": code,
                    "entry_date": position["entry_date"],
                    "planned_exit_date": due,
                    "market_value": value,
                    "weight": value / equity,
                    "units": position["units"],
                    "exit_delayed": due is not None and date >= due,
                }
            )
        self.daily.append(
            {
                "top_n": self.n,
                "trade_date": date,
                "net_value": equity,
                "net_return": equity / self.previous_equity - 1,
                "gross_return": (equity + fees) / self.previous_equity - 1,
                "transaction_cost": fees / self.previous_equity,
                "turnover": (bought + sold) / self.previous_equity,
                "cash": self.cash,
                "cash_weight": self.cash / equity,
                "count": len(self.book),
                "open_positions": len(self.book),
                "delayed_open_positions": sum(
                    p["planned_exit_date"] is not None and date >= p["planned_exit_date"] for p in self.book.values()
                ),
                "unsettled_positions": len(self.book),
                "delayed_exits": delayed_exits,
                "unfilled_entries": unfilled,
            }
        )
        if self.events is not None:
            self.daily[-1]["pending_cash"] = pending_cash
        self.previous_equity = equity

    def _sell(self, date, quotes, ranks, limit, signal_date) -> tuple[float, float, int]:
        fees = sold = 0.0
        count = delayed = 0
        held = (
            sorted(self.book, key=lambda code: (-ranks.get(code, math.inf), code))
            if self.policy is not None
            else list(self.book)
        )
        for code in held:
            position = self.book[code]
            quote = quotes.get(code)
            status = self._quote_status(quote)
            if status == "quoted":
                position["mark"] = quote["price"] * quote["adjustment_factor"]
                if self.events is not None:
                    position["last_factor"] = quote["adjustment_factor"]
            elif status == "missing_data":
                self.incomplete = True
            due = position["planned_exit_date"]
            eligible = (
                signal_date
                and self.policy.should_exit(
                    rank=ranks.get(code),
                    age=self.date_indices[date] - self.date_indices[position["entry_date"]],
                    n=self.n,
                )
                if self.policy is not None
                else due is not None and date >= due
            )
            if not eligible or count >= limit:
                continue
            if status != "quoted" or not quote["can_sell"]:
                self._order(date, code, "sell", reason=status if status != "quoted" else "not_sellable")
                continue
            notional = position["units"] * position["mark"]
            fee = notional * self.config.sell_cost_rate
            self.cash += notional - fee
            sold += notional
            fees += fee
            count += 1
            delayed += due is not None and date > due
            self._order(date, code, "sell", notional=notional, fee=fee)
            self.trades.append(
                {
                    "top_n": self.n,
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
            del self.book[code]
        return fees, sold, delayed

    def _buy(self, date, quotes, signals, limit, allocation) -> tuple[float, float, int]:
        fees = bought = 0.0
        count = unfilled = 0
        for signal in signals:
            code = signal["ts_code"]
            if code in self.book or count >= limit:
                continue
            quote = quotes.get(code)
            status = self._quote_status(quote)
            blocked = self.events is not None and self.events.blocked(code)
            if status == "missing_data" and not blocked:
                self.incomplete = True
            if blocked:
                reason = "security_event"
            elif status != "quoted":
                reason = status
            elif not quote["can_buy"]:
                reason = "not_buyable"
            elif len(self.book) >= self.n:
                reason = "capacity"
            else:
                reason = ""
            principal = min(allocation, self.cash / (1 + self.config.buy_cost_rate)) if not reason else 0.0
            if principal <= 1e-12:
                unfilled += 1
                self._order(date, code, "buy", reason=reason or "cash")
                continue
            holding_days = self.config.holding_days
            index = self.date_indices[date] + holding_days if holding_days is not None else len(self.calendar)
            due = self.calendar[index] if index < len(self.calendar) else None
            price = quote["price"] * quote["adjustment_factor"]
            fee = principal * self.config.buy_cost_rate
            self.book[code] = {
                "units": principal / price,
                "mark": price,
                "principal": principal,
                "entry_price": quote["price"],
                "entry_fee": fee,
                "entry_date": date,
                "planned_exit_date": due,
            }
            if self.events is not None:
                self.book[code].update(
                    entry_shares=principal / quote["price"],
                    entry_factor=quote["adjustment_factor"],
                    last_factor=quote["adjustment_factor"],
                )
            self.cash -= principal + fee
            fees += fee
            bought += principal
            count += 1
            self._order(date, code, "buy", notional=principal, fee=fee)
        return fees, bought, unfilled

    def _order(self, date, code, side, *, reason="", notional=0.0, fee=0.0) -> None:
        self.orders.append(
            {
                "top_n": self.n,
                "trade_date": date,
                "ts_code": code,
                "side": side,
                "status": "unfilled" if reason else "filled",
                "reason": reason,
                "notional": notional,
                "fee": fee,
            }
        )

    def _equity(self, pending_cash: float) -> float:
        return self.cash + pending_cash + sum(p["units"] * p["mark"] for p in self.book.values())

    def _quote_status(self, quote) -> str:
        status = quote["market_status"] if quote else "missing_data"
        if status == "missing_data" and self.config.missing_market_as_suspension:
            return "suspended"
        return status

    def _replacement_limit(self) -> int:
        limit = self.policy.replacement_limit(self.n) if self.policy is not None else self.n
        if not 1 <= limit <= self.n:
            raise ValueError("Portfolio policy replacement limit must be between 1 and N")
        return limit

    def frames(self) -> dict[str, pl.DataFrame]:
        """Publish typed records chronologically, preserving configured Top N order."""
        n_order = {n: index for index, n in enumerate(self.config.top_ns)}
        frames = {}
        for name, schema in RECORD_SCHEMAS.items():
            rows = getattr(self, name)
            rows.sort(key=lambda row: (row.get("trade_date", row.get("exit_date")), n_order[row["top_n"]]))
            frames[name] = pl.DataFrame(rows, schema=schema)
        return frames


RECORD_SCHEMAS = {
    "orders": {
        "top_n": pl.Int64,
        "trade_date": pl.String,
        "ts_code": pl.String,
        "side": pl.String,
        "status": pl.String,
        "reason": pl.String,
        "notional": pl.Float64,
        "fee": pl.Float64,
    },
    "positions": {
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
    "trades": {
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
}
