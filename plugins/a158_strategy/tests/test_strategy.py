"""Bounded replacements, ledger accounting, and unavailable quote regressions."""

import polars as pl
import pytest
from axonx_alpha158_strategy.backtest import RankRetentionPolicy, StrategyBacktestInput
from axonx.task.builtins.stock.engine import BacktestConfig, run_backtest


def fixture():
    dates = [f"202301{i + 1:02d}" for i in range(16)]
    symbols = "ABCDEFGHIJ"
    signals, market = [], []
    for i, date in enumerate(dates):
        order = symbols if i == 0 else symbols[5:] + symbols[:5]
        for rank, code in enumerate(order):
            signals.append(
                {
                    "trade_date": date,
                    "trade_time": "1500",
                    "ts_code": code,
                    "pred": 1.0 - rank * 0.01,
                    "is_model_candidate": True,
                    "is_buyable_at_signal": True,
                    "signal_price": 1.0,
                    "signal_adjustment_factor": 1.0,
                }
            )
            missing = code == "E" and i == 1
            market.append(
                {
                    "trade_date": date,
                    "trade_time": "1500",
                    "ts_code": code,
                    "price": None if missing else 1 + i * 0.01,
                    "adjustment_factor": 1.0,
                    "market_status": "missing_data" if missing else "quoted",
                    "can_buy": not missing,
                    "can_sell": not missing and not (code == "D" and i == 1),
                }
            )
    return pl.DataFrame(signals), pl.DataFrame(market), pl.DataFrame({"trade_date": dates})


@pytest.mark.parametrize(
    "minimum,buffer,cap,first_date,first_code",
    [(0, 1.0, 0.2, "20230102", "C"), (3, 1.5, 0.4, "20230104", "E"), (10, 1.0, 0.2, "20230111", "E")],
)
def test_policy_respects_rank_age_and_filled_order_caps(minimum, buffer, cap, first_date, first_code):
    signals, market, calendar = fixture()
    result = run_backtest(
        signals,
        market,
        calendar,
        None,
        BacktestConfig(top_ns=(5,)),
        as_of_date="20230116",
        policy=RankRetentionPolicy(cap, minimum, buffer),
    )
    filled = result.frames["orders"].filter(pl.col("status") == "filled")
    initial = filled.filter(pl.col("trade_date") == "20230101")
    assert initial["ts_code"].to_list() == list("ABCDE")
    sells = filled.filter(pl.col("side") == "sell")
    assert sells.row(0, named=True)["trade_date"] == first_date
    assert sells.row(0, named=True)["ts_code"] == first_code
    if minimum == 0:
        blocked = result.frames["orders"].filter((pl.col("trade_date") == "20230102") & (pl.col("side") == "sell"))
        assert blocked.select("ts_code", "status", "reason").rows() == [
            ("E", "unfilled", "missing_data"),
            ("D", "unfilled", "not_sellable"),
            ("C", "filled", ""),
        ]
    previous_equity = 1.0
    for row in result.frames["daily"].iter_rows(named=True):
        date = row["trade_date"]
        positions = result.frames["positions"].filter(pl.col("trade_date") == date)
        assert row["top5_cash"] + positions["market_value"].sum() == pytest.approx(row["top5_net_value"])
        assert positions.height <= 5
        fees = filled.filter(pl.col("trade_date") == date)["fee"].sum()
        assert row["top5_transaction_cost"] == pytest.approx(fees / previous_equity)
        previous_equity = row["top5_net_value"]
    orders = result.frames["orders"].filter((pl.col("status") == "filled") & (pl.col("trade_date") > "20230101"))
    assert orders.group_by("trade_date", "side").len()["len"].max() <= int(5 * cap)
    assert result.status == "incomplete_market_data"
    assert result.frames["positions"]["planned_exit_date"].null_count() == result.frames["positions"].height
    assert not result.frames["trades"]["exit_delayed"].any()


def test_future_scores_do_not_change_prefix_decisions():
    signals, market, calendar = fixture()
    config, policy = BacktestConfig(top_ns=(5,)), RankRetentionPolicy(0.2, 0, 1.0)
    full = run_backtest(signals, market, calendar, None, config, as_of_date="20230116", policy=policy)
    prefix = run_backtest(signals, market, calendar, None, config, as_of_date="20230104", policy=policy)
    assert full.frames["orders"].filter(pl.col("trade_date") <= "20230104").equals(prefix.frames["orders"])


def test_fixed_expiry_cannot_be_silently_configured():
    with pytest.raises(ValueError):
        StrategyBacktestInput(holding_days=5)


def test_missing_framework_extension_fails_instead_of_running_fixed_expiry(monkeypatch):
    from axonx_alpha158_strategy.backtest import StrategyBacktestTask
    from axonx.task.builtins.stock.backtest import BaseStockBacktestTask

    monkeypatch.delattr(BaseStockBacktestTask, "portfolio_policy")
    task = object.__new__(StrategyBacktestTask)
    with pytest.raises(RuntimeError, match="portfolio_policy extension"):
        list(task.build_task_steps())


@pytest.mark.parametrize("n,fraction,expected", [(1, 0.2, 1), (3, 0.2, 1), (5, 0.2, 1), (30, 0.2, 6)])
def test_replacement_limit_rounds_down_with_minimum_one(n, fraction, expected):
    assert RankRetentionPolicy(fraction, 10, 1.0).replacement_limit(n) == expected


def test_rank_buffer_retains_eligible_holdings():
    policy = RankRetentionPolicy(0.2, 3, 1.5)
    assert not policy.should_exit(rank=8, age=3, n=5)
    assert not policy.should_exit(rank=9, age=2, n=5)
    assert policy.should_exit(rank=9, age=3, n=5)
    assert policy.should_exit(rank=None, age=3, n=5)


@pytest.mark.parametrize("fraction", [0.0, 1.1])
def test_invalid_replacement_fraction_is_rejected(fraction):
    with pytest.raises(ValueError):
        StrategyBacktestInput(replacement_fraction=fraction)
