"""One mark-to-market cash/position ledger for stock prediction backtests."""

from dataclasses import dataclass
import math
from typing import Any, Protocol

import polars as pl

from .data import KEYS, MARKET_COLUMNS, SIGNAL_COLUMNS, normalize_calendar, normalize_keys, validate_keys


class PortfolioPolicy(Protocol):
    """Plugin decision hook; the engine retains ownership of execution and cash."""

    def replacement_limit(self, n: int) -> int:
        """Maximum successful buys and sells per day, after initial construction."""

    def should_exit(self, *, rank: int | None, age: int, n: int) -> bool:
        """Decide using current candidate rank and elapsed market days only."""


@dataclass(frozen=True)
class BacktestConfig:
    top_ns: tuple[int, ...] = (1, 2, 3, 5, 10, 20, 30)
    holding_days: int = 1
    transaction_cost_rate: float = 0.002  # charged on each executed side
    annual_risk_free_rate: float = 0.012
    annualization_days: int = 252
    minimum_index_weight_coverage: float = 0.98
    index_codes: tuple[str, ...] = ()
    buy_cost_rate: float | None = None
    sell_cost_rate: float | None = None


@dataclass
class BacktestResult:
    frames: dict[str, pl.DataFrame]
    benchmark_keys: tuple[str, ...]
    status: str


def _execution_cost_rates(config: BacktestConfig) -> tuple[float, float]:
    """Resolve optional side rates without treating an explicit zero as unset."""
    if not 0 <= config.transaction_cost_rate < 1:
        raise ValueError("transaction_cost_rate must be in [0,1)")
    buy_cost_rate = config.transaction_cost_rate if config.buy_cost_rate is None else config.buy_cost_rate
    sell_cost_rate = config.transaction_cost_rate if config.sell_cost_rate is None else config.sell_cost_rate
    if not 0 <= buy_cost_rate < 1 or not 0 <= sell_cost_rate < 1:
        raise ValueError("buy_cost_rate and sell_cost_rate must be in [0,1)")
    return buy_cost_rate, sell_cost_rate


def run_backtest(
    signals: pl.DataFrame,
    market: pl.DataFrame,
    calendar: pl.DataFrame,
    labels: pl.DataFrame | None,
    config: BacktestConfig,
    *,
    as_of_date: str,
    policy: PortfolioPolicy | None = None,
) -> BacktestResult:
    if not config.top_ns or any(n < 1 for n in config.top_ns) or config.holding_days < 1:
        raise ValueError("Positive top_ns and holding_days are required")
    buy_cost_rate, sell_cost_rate = _execution_cost_rates(config)
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
    if not set(signals["trade_date"]).issubset(all_dates):
        raise ValueError("Signal dates must belong to the market calendar")
    dates = [d for d in all_dates if signals["trade_date"].min() <= d <= as_of_date]
    if not dates:
        raise ValueError("No calendar dates within evaluation cutoff")
    targets = _candidates(signals.filter(pl.col("trade_date") <= as_of_date), config)
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
    groups = {key[0]: frame.to_dicts() for key, frame in selected.partition_by("trade_date", as_dict=True).items()}
    by_date = {d: groups.get(d, []) for d in dates}
    daily, orders, positions, trades = [], [], [], []
    incomplete = False
    portfolios = {n: {"cash": 1.0, "equity": 1.0, "book": {}} for n in config.top_ns}
    for date in dates:
        needed = {row["ts_code"] for row in by_date[date]} | {
            code for portfolio in portfolios.values() for code in portfolio["book"]
        }
        day_market = market_days.get(date)
        quotes = (
            {row["ts_code"]: row for row in day_market.filter(pl.col("ts_code").is_in(needed)).to_dicts()}
            if day_market is not None
            else {}
        )
        for n in config.top_ns:
            portfolio = portfolios[n]
            cash, previous_equity, book = portfolio["cash"], portfolio["equity"], portfolio["book"]
            fees = bought = sold = 0.0
            sell_count = buy_count = 0
            limit = _replacement_limit(policy, n) if date != dates[0] else n
            ranks = ranks_by_date.get(date, {})
            delayed_exits = unfilled = 0
            held = (
                sorted(book, key=lambda code, current=ranks: (-current.get(code, math.inf), code))
                if policy is not None
                else list(book)
            )
            for code in held:
                position = book[code]
                quote = quotes.get(code)
                status = quote["market_status"] if quote else "missing_data"
                if status == "quoted":
                    position["mark"] = quote["price"] * quote["adjustment_factor"]
                elif status == "missing_data":
                    incomplete = True
                due = position["planned_exit_date"]
                eligible = (
                    policy.should_exit(
                        rank=ranks.get(code), age=date_indices[date] - date_indices[position["entry_date"]], n=n
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
            equity = cash + sum(p["units"] * p["mark"] for p in book.values())
            allocation = equity / n
            for signal in by_date[date][:n]:
                code = signal["ts_code"]
                if code in book or buy_count >= limit:
                    continue
                quote = quotes.get(code)
                status = quote["market_status"] if quote else "missing_data"
                if status == "missing_data":
                    incomplete = True
                reason = (
                    status
                    if status != "quoted"
                    else ("not_buyable" if not quote["can_buy"] else "capacity" if len(book) >= n else "")
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
                index = date_indices[date] + config.holding_days
                due = all_dates[index] if policy is None and index < len(all_dates) else None
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
            equity = cash + sum(p["units"] * p["mark"] for p in book.values())
            if cash < -1e-10 or equity <= 0:
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
                        (p["planned_exit_date"] is not None and date >= p["planned_exit_date"] for p in book.values())
                    ),
                    "unsettled_positions": len(book),
                    "delayed_exits": delayed_exits,
                    "unfilled_entries": unfilled,
                }
            )
            portfolio.update(cash=cash, equity=equity)
    daily_long = pl.DataFrame(daily)
    output = pl.DataFrame({"trade_date": dates})
    for n in config.top_ns:
        part = daily_long.filter(pl.col("top_n") == n).drop("top_n")
        output = output.join(
            part.rename({c: f"top{n}_{c}" for c in part.columns if c != "trade_date"}),
            on="trade_date",
            validate="1:1",
        )
    diagnostics, benchmarks = _diagnostics(signals, targets, labels, as_of_date, config)
    output = output.join(diagnostics, on="trade_date", how="left").with_columns(
        pl.col("ic", "rank_ic").cast(pl.Float64)
    )
    if labels is not None:
        target_labels = (
            normalize_keys(labels)
            .filter(pl.col("label_valid") & (pl.col("label_target_date").cast(pl.String) <= as_of_date))
            .select(*KEYS, pl.col("label_return").alias("_target_return"))
        )
        targets = targets.join(target_labels, on=list(KEYS), how="left", validate="1:1")
    else:
        targets = targets.with_columns(pl.lit(None, dtype=pl.Float64).alias("_target_return"))
    details = targets.group_by("trade_date").agg(
        pl.len().alias("candidate_count"),
        pl.struct(
            pl.col("target_rank").alias("rank"),
            "ts_code",
            (pl.col("name") if "name" in targets.columns else pl.col("ts_code").alias("name")),
            pl.col("pred").alias("prediction"),
            pl.col("_target_return").alias("daily_return"),
            (1.0 / pl.min_horizontal(pl.len(), pl.lit(30))).alias("weight"),
        )
        .filter(pl.col("target_rank") <= 30)
        .alias("top30_holdings"),
    )
    output = output.join(details, on="trade_date", how="left").with_columns(pl.col("candidate_count").fill_null(0))
    frames = {
        "daily": output,
        "summary": _summarize(
            output, benchmarks, config.annual_risk_free_rate, config.annualization_days, config.top_ns
        ),
        "targets": targets.rename({"_target_return": "label_return"}),
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


def _frame(rows: list[dict[str, Any]], schema: dict[str, Any]) -> pl.DataFrame:
    return pl.DataFrame(rows, schema=schema)


def _candidates(signals: pl.DataFrame, config: BacktestConfig) -> pl.DataFrame:
    candidates = signals.filter(pl.col("is_model_candidate") & pl.col("is_buyable_at_signal"))
    if config.index_codes:
        columns = [f"index_weight_{code}" for code in config.index_codes]
        if set(columns) - set(candidates.columns):
            raise ValueError("Missing requested index weights")
        candidates = candidates.filter(pl.any_horizontal(*(pl.col(c) > 0 for c in columns)))
    return candidates.sort(["trade_date", "pred", "ts_code"], descending=[False, True, False]).with_columns(
        pl.int_range(1, pl.len() + 1).over("trade_date").alias("target_rank")
    )


def _diagnostics(
    signals: pl.DataFrame,
    candidates: pl.DataFrame,
    labels: pl.DataFrame | None,
    cutoff: str,
    config: BacktestConfig,
) -> tuple[pl.DataFrame, tuple[str, ...]]:
    dates = signals.select("trade_date").unique()
    if labels is None:
        return (
            dates.with_columns(
                pl.lit(None, dtype=pl.Float64).alias("ic"),
                pl.lit(None, dtype=pl.Float64).alias("rank_ic"),
                *(pl.lit(None, dtype=pl.Float64).alias(f"top{n}_ndcg") for n in config.top_ns),
            ),
            (),
        )
    labels = normalize_keys(labels)
    validate_keys(labels)
    joined = signals.join(labels, on=list(KEYS), how="left", validate="1:1").filter(
        pl.col("label_valid") & (pl.col("label_target_date").cast(pl.String) <= cutoff)
    )
    matured = candidates.join(joined.select(*KEYS, "label_return"), on=list(KEYS), how="inner", validate="1:1")
    diagnostics = matured.group_by("trade_date").agg(
        pl.corr("pred", "label_return").alias("ic"),
        pl.corr("pred", "label_return", method="spearman").alias("rank_ic"),
    )
    quality = []
    for key, data in matured.partition_by("trade_date", as_dict=True).items():
        actual = data["label_return"]
        relevance = (actual.rank(method="average") / len(actual)).to_list()
        rows = list(zip(data["target_rank"].to_list(), relevance, strict=True))
        ideal = sorted(relevance, reverse=True)
        row = {"trade_date": key[0]}
        for n in config.top_ns:
            dcg = sum((2**v - 1) / math.log2(rank + 1) for rank, v in rows if rank <= n)
            idcg = sum((2**v - 1) / math.log2(rank + 2) for rank, v in enumerate(ideal[:n]))
            row[f"top{n}_ndcg"] = dcg / idcg if idcg else None
        quality.append(row)
    schema = {"trade_date": pl.String, **{f"top{n}_ndcg": pl.Float64 for n in config.top_ns}}
    diagnostics = diagnostics.join(
        pl.DataFrame(quality, schema=schema), on="trade_date", how="full", coalesce=True
    ).with_columns(pl.when(pl.col(c).is_finite()).then(pl.col(c)).otherwise(None).alias(c) for c in ("ic", "rank_ic"))
    weights = [c for c in signals.columns if c.startswith("index_weight_")]
    benchmarks = ("universe", *(c.removeprefix("index_weight_") for c in weights))
    returns = (
        joined.group_by("label_target_date")
        .agg(
            pl.col("label_return").mean().alias("benchmark_universe_return"),
            *(
                pl.when(pl.col(c).sum() >= config.minimum_index_weight_coverage)
                .then((pl.col(c) * pl.col("label_return")).sum() / pl.col(c).sum())
                .alias(f"benchmark_{c.removeprefix('index_weight_')}_return")
                for c in weights
            ),
        )
        .rename({"label_target_date": "trade_date"})
    )
    # Signal diagnostics and valuation-period benchmarks have different date axes.
    return (
        dates.join(diagnostics, on="trade_date", how="left").join(returns, on="trade_date", how="full", coalesce=True),
        benchmarks,
    )


def _ratio(column: str) -> pl.Expr:
    values = pl.col(column).drop_nulls()
    std = values.std(ddof=1)
    return pl.when((values.len() > 1) & (std > 0)).then(values.mean() / std).otherwise(0.0)


def _period_column(period_type: str) -> pl.Expr:
    if period_type == "overall":
        return pl.lit("all")
    if period_type == "year":
        return pl.col("trade_date").str.slice(0, 4)
    if period_type == "quarter":
        month = pl.col("trade_date").str.slice(4, 2).cast(pl.Int8)
        return pl.col("trade_date").str.slice(0, 4) + "Q" + (((month - 1) // 3) + 1).cast(pl.String)
    return pl.col("trade_date").str.slice(0, 4) + "-" + pl.col("trade_date").str.slice(4, 2)


def _summarize(
    daily: pl.DataFrame,
    benchmark_keys: tuple[str, ...],
    annual_risk_free_rate: float,
    annualization_days: int,
    top_ns: tuple[int, ...],
) -> pl.DataFrame:
    return pl.concat(
        [
            _summarize_period(
                daily,
                period_type,
                benchmark_keys,
                annual_risk_free_rate,
                annualization_days,
                top_ns,
            )
            for period_type in ("overall", "year", "quarter", "month")
        ],
        how="vertical",
    )


def _summarize_period(
    daily: pl.DataFrame,
    period_type: str,
    benchmark_keys: tuple[str, ...],
    annual_risk_free_rate: float,
    annualization_days: int,
    top_ns: tuple[int, ...],
) -> pl.DataFrame:
    daily_rf = (1 + annual_risk_free_rate) ** (1 / annualization_days) - 1
    frame = daily.with_columns(_period_column(period_type).alias("_period")).sort(
        "_period",
        "trade_date",
    )
    derived: list[pl.Expr] = []
    for top_n in top_ns:
        prefix = f"top{top_n}"
        derived.extend(
            (
                (pl.col(f"{prefix}_net_return") + 1).cum_prod().over("_period").alias(f"_{prefix}_equity"),
                (pl.col(f"{prefix}_gross_return") - daily_rf).alias(
                    f"_{prefix}_gross_excess",
                ),
            ),
        )
        derived.extend(
            (pl.col(f"{prefix}_gross_return") - pl.col(f"benchmark_{key}_return")).alias(f"_{prefix}_{key}_active")
            for key in benchmark_keys
        )
    frame = frame.with_columns(*derived)
    annual_scale = math.sqrt(annualization_days)
    metrics: list[pl.Expr] = [
        pl.col("trade_date").min().alias("period_start"),
        pl.col("trade_date").max().alias("period_end"),
        pl.len().alias("trading_days"),
        pl.col("ic").mean().alias("ic_mean"),
        (_ratio("ic") * annual_scale).alias("icir"),
        pl.col("rank_ic").mean().alias("rank_ic_mean"),
        (_ratio("rank_ic") * annual_scale).alias("rank_icir"),
    ]
    for top_n in top_ns:
        prefix = f"top{top_n}"
        net = f"{prefix}_net_return"
        equity = f"_{prefix}_equity"
        cumulative = (pl.col(net) + 1).product()
        peak = pl.max_horizontal(pl.lit(1.0), pl.col(equity).cum_max().over("_period"))
        metrics.extend(
            (
                (cumulative - 1).alias(f"{prefix}_net_cumulative_return"),
                pl.when(cumulative > 0)
                .then(cumulative.pow(annualization_days / pl.len()) - 1)
                .otherwise(-1.0)
                .alias(f"{prefix}_net_annualized_return"),
                (pl.col(net).std(ddof=1) * annual_scale).alias(
                    f"{prefix}_net_annualized_volatility",
                ),
                (pl.col(equity) / peak - 1).min().alias(f"{prefix}_net_max_drawdown"),
                (pl.col(net) > 0).mean().alias(f"{prefix}_net_win_rate"),
                pl.col(f"{prefix}_turnover").mean().alias(f"{prefix}_average_turnover"),
                pl.col(f"{prefix}_delayed_exits").sum().alias(f"{prefix}_delayed_exits"),
                pl.col(f"{prefix}_unsettled_positions").last().alias(f"{prefix}_unsettled_positions"),
                ((pl.col(f"{prefix}_gross_return") + 1).product() - 1).alias(
                    f"{prefix}_gross_cumulative_return",
                ),
                (_ratio(f"_{prefix}_gross_excess") * annual_scale).alias(
                    f"{prefix}_gross_sharpe",
                ),
            ),
        )
        metrics.extend(
            (_ratio(f"_{prefix}_{key}_active") * annual_scale).alias(
                f"{prefix}_information_ratio_{key}",
            )
            for key in benchmark_keys
        )
    return (
        frame.group_by("_period", maintain_order=True)
        .agg(*metrics)
        .rename({"_period": "period"})
        .with_columns(pl.lit(period_type).alias("period_type"))
        .select("period_type", "period", pl.exclude("period_type", "period"))
    )
