"""Stock ledger accounting, event ownership and cutoff-safe report regressions."""

import polars as pl
import pytest

from axonx.task.builtins.stock.backtest import BaseStockBacktestTask
from axonx.task.builtins.stock.data import fixed_labels
from axonx.task.builtins.stock.engine import run_backtest
from axonx.task.builtins.stock.models import BacktestConfig, portfolio_key
from axonx.task.builtins.stock.portfolio import BaseStockPortfolioTask, portfolio_identity, prepare_portfolio_signals
from axonx.task.builtins.stock.reporting import online_frames, summarize
from axonx.task.runtime.executor import TaskExecutor


def market_inputs(statuses=("quoted", "quoted", "quoted", "quoted")):
    dates = [f"2024010{day}" for day in range(1, 5)]
    signals = pl.DataFrame(
        {
            "trade_date": [dates[0]],
            "trade_time": ["1500"],
            "ts_code": ["A"],
            "pred": [1.0],
            "is_model_candidate": [True],
            "is_buyable_at_signal": [True],
            "signal_price": [1.0],
            "signal_adjustment_factor": [1.0],
        }
    )
    market = pl.DataFrame(
        {
            "trade_date": dates,
            "trade_time": ["1500"] * 4,
            "ts_code": ["A"] * 4,
            "price": [1.0 + index / 10 if status == "quoted" else None for index, status in enumerate(statuses)],
            "adjustment_factor": [1.0] * 4,
            "market_status": statuses,
            "can_buy": [status == "quoted" for status in statuses],
            "can_sell": [status == "quoted" for status in statuses],
        }
    )
    return signals, market, pl.DataFrame({"trade_date": dates})


def test_online_ledgers_share_predictions_and_publish_only_daily_portfolio_rows():
    signals, market, calendar = market_inputs()
    result = run_backtest(
        prepare_portfolio_signals(signals),
        market,
        calendar,
        None,
        BacktestConfig(top_ns=(1, 30), buy_cost_rate=0, sell_cost_rate=0),
        as_of_date="20240102",
    )
    identities = [
        portfolio_identity(
            universe={"kind": "all"},
            score_selection={"method": "seed", "seeds": [0]},
            strategy={"kind": "fixed_expiry", "holding_days": 1},
            top_n=n,
            trade_time="1500",
        )
        for n in (1, 30)
    ]
    frames = online_frames(result.frames, "20240102", {portfolio_key(identity): identity for identity in identities})
    assert frames["daily"].height == 2
    assert frames["daily"]["trade_date"].to_list() == ["20240102"] * 2
    assert not any(dtype.is_nested() for dtype in frames["daily"].schema.values())
    assert frames["positions"].is_empty()
    assert frames["trades"]["exit_date"].to_list() == ["20240102"] * 2
    for identity in identities:
        key = portfolio_key(identity)
        row = frames["daily"].filter(pl.col("portfolio_key") == key).row(0, named=True)
        assert row["net_value"] == result.frames["daily"][f"top{identity['top_n']}_net_value"][-1]
        assert frames["summary"].filter(pl.col("portfolio_key") == key).height == 4


@pytest.mark.parametrize("assume_suspension", [False, True])
def test_unavailable_quotes_carry_marks_and_delay_fixed_exits(assume_suspension):
    signals, market, calendar = market_inputs(("quoted", "suspended", "missing_data", "quoted"))
    labels = fixed_labels(signals, market, calendar)
    assert labels.select("label_target_date", "label_valid", "label_status").row(0) == ("20240102", False, "suspended")
    result = run_backtest(
        prepare_portfolio_signals(signals),
        market,
        calendar,
        labels,
        BacktestConfig(top_ns=(1,), buy_cost_rate=0, sell_cost_rate=0, missing_market_as_suspension=assume_suspension),
        as_of_date="20240104",
    )
    assert result.status == ("done" if assume_suspension else "incomplete_market_data")
    assert result.frames["daily"]["top1_net_value"].to_list() == pytest.approx([1, 1, 1, 1.3])
    assert result.frames["trades"].select("planned_exit_date", "exit_date", "exit_delayed").row(0) == (
        "20240102",
        "20240104",
        True,
    )
    assert result.frames["positions"]["market_value"].to_list() == [1, 1, 1]
    assert "signals" not in result.frames


def test_event_receivables_and_books_are_reset_for_every_portfolio():
    class Events:
        successors = set()

        def __init__(self):
            self.resets = []
            self.pending_cash = self.transaction_cost = self.executed_notional = 0.0

        def reset(self, n):
            self.resets.append(n)
            self.pending_cash = 0.0

        def blocked(self, _code):
            return False

        def apply(self, date, slot, book, cash, _quotes):
            assert slot == "1500"
            if date == "20240102":
                (position,) = book.pop("A")
                assert position["entry_factor"] == position["last_factor"] == 1
                self.pending_cash = position["entry_shares"]
            if date == "20240103":
                cash += self.pending_cash
                self.pending_cash = 0.0
            return cash

    events = Events()
    signals, market, calendar = market_inputs()
    result = run_backtest(
        prepare_portfolio_signals(signals),
        market,
        calendar,
        None,
        BacktestConfig(top_ns=(1, 2), holding_days=10, buy_cost_rate=0, sell_cost_rate=0),
        as_of_date="20240104",
        events=events,
    )
    assert events.resets == [1, 2]
    daily = result.frames["daily"]
    for n, receivable in [(1, 1.0), (2, 0.5)]:
        assert daily[f"top{n}_net_value"].to_list() == [1.0] * 4
        assert daily[f"top{n}_pending_cash"].to_list() == [0.0, receivable, 0.0, 0.0]
        assert daily[f"top{n}_open_positions"].to_list() == [1, 0, 0, 0]
    assert result.frames["trades"].is_empty()
    assert result.frames["trades"].schema["planned_exit_date"] == pl.String


def test_event_costs_and_notional_are_counted_once_at_recognition():
    class Events:
        successors = set()

        def __init__(self):
            self.pending_cash = self.transaction_cost = self.executed_notional = 0.0

        def reset(self, _n):
            self.pending_cash = self.transaction_cost = self.executed_notional = 0.0

        def blocked(self, _code):
            return False

        def apply(self, date, _slot, book, cash, _quotes):
            self.transaction_cost = self.executed_notional = 0.0
            if date == "20240102":
                book.pop("A")
                self.pending_cash = 0.99
                self.transaction_cost = 0.01
                self.executed_notional = 1.0
            if date == "20240103":
                cash += self.pending_cash
                self.pending_cash = 0.0
            return cash

    signals, market, calendar = market_inputs()
    result = run_backtest(
        prepare_portfolio_signals(signals),
        market,
        calendar,
        None,
        BacktestConfig(top_ns=(1,), holding_days=10, buy_cost_rate=0, sell_cost_rate=0),
        as_of_date="20240104",
        events=Events(),
    )
    daily = result.frames["daily"]
    assert daily["top1_net_value"].to_list() == pytest.approx([1, 0.99, 0.99, 0.99])
    assert daily["top1_pending_cash"].to_list() == pytest.approx([0, 0.99, 0, 0])
    assert daily["top1_transaction_cost"].to_list() == pytest.approx([0, 0.01, 0, 0])
    assert daily["top1_gross_return"].to_list() == pytest.approx([0, 0, 0, 0])
    assert daily["top1_turnover"].to_list() == pytest.approx([1, 1, 0, 0])


def test_backtest_task_publishes_reconciled_ledger_artifacts(tmp_path):
    signals, market, calendar = market_inputs()
    for name, frame in [("input", signals), ("market", market), ("calendar", calendar)]:
        frame.write_parquet(tmp_path / f"{name}.parquet")
    portfolio = BaseStockPortfolioTask(
        {"input_file": "input.parquet", "top_ns": [1], "holding_days": 2},
        workspace_path=tmp_path,
        reg_name="stock",
    )
    TaskExecutor().execute(portfolio)
    task = BaseStockBacktestTask(
        {
            "task_name": "ledger",
            "upstream_task_ids": [portfolio.task_id],
            "market_file": "market.parquet",
            "calendar_file": "calendar.parquet",
        },
        workspace_path=tmp_path,
        reg_name="stock",
    )
    TaskExecutor().execute(task)
    output = task.output_params
    assert output.portfolios[0].evaluation_status == "done"
    daily = pl.read_parquet(task.artifact_path("0_daily"))
    positions = pl.read_parquet(task.artifact_path("0_positions"))
    orders = pl.read_parquet(task.artifact_path("0_orders"))
    previous = 1.0
    for row in daily.iter_rows(named=True):
        date = row["trade_date"]
        value = positions.filter(pl.col("trade_date") == date)["market_value"].sum()
        fees = orders.filter(pl.col("trade_date") == date)["fee"].sum()
        assert row["top1_cash"] + value == pytest.approx(row["top1_net_value"])
        assert row["top1_transaction_cost"] == pytest.approx(fees / previous)
        previous = row["top1_net_value"]


def test_relative_drawdown_uses_aligned_active_returns_and_resets_each_period():
    daily = pl.DataFrame(
        {
            "trade_date": ["20240131", "20240201", "20240202"],
            "ic": pl.Series([None] * 3, dtype=pl.Float64),
            "rank_ic": pl.Series([None] * 3, dtype=pl.Float64),
            "top1_net_return": [-0.1, 0.1, -0.2],
            "top1_gross_return": [-0.1, 0.1, -0.2],
            "benchmark_universe_return": [0.1, None, -0.1],
            "top1_turnover": [0.0] * 3,
            "top1_delayed_exits": [0] * 3,
            "top1_unsettled_positions": [0] * 3,
        }
    )
    summary = summarize(daily, ("universe",), 0.0, 252, (1,))
    column = "top1_net_relative_max_drawdown_universe"
    assert summary.filter(pl.col("period_type") == "overall")[column].item() == pytest.approx(-0.28)
    assert summary.filter(pl.col("period_type") == "month")[column].to_list() == pytest.approx([-0.2, -0.1])
