"""Shared accounting and cutoff regression tests, without external data."""

import polars as pl
import pytest

from axonx.task.builtins.stock.data import fixed_labels, transform_labels
from axonx.task.builtins.stock.engine import BacktestConfig, run_backtest


def inputs():
    calendar = pl.DataFrame({"trade_date": ["20260105", "20260106", "20260107", "20260108"]})
    signals = pl.DataFrame(
        {
            "trade_date": ["20260105", "20260106"],
            "trade_time": ["1445"] * 2,
            "ts_code": ["A", "B"],
            "name": ["A", "B"],
            "pred": [2.0, 3.0],
            "is_model_candidate": [True] * 2,
            "is_buyable_at_signal": [True] * 2,
            "signal_price": [10.0, 20.0],
            "signal_adjustment_factor": [1.0] * 2,
        }
    )
    market = pl.DataFrame(
        {
            "trade_date": [
                "20260105",
                "20260106",
                "20260107",
                "20260108",
                "20260106",
                "20260107",
                "20260108",
            ],
            "trade_time": ["1445"] * 7,
            "ts_code": ["A"] * 4 + ["B"] * 3,
            "price": [10.0, None, 11.0, 12.0, 20.0, 22.0, 24.0],
            "adjustment_factor": [1.0] * 7,
            "can_buy": [True, False, True, True, True, True, True],
            "can_sell": [True, False, True, True, True, True, True],
            "market_status": [
                "quoted",
                "suspended",
                "quoted",
                "quoted",
                "quoted",
                "quoted",
                "quoted",
            ],
        }
    )
    return signals, market, calendar


def test_suspension_invalidates_fixed_label_without_searching_to_resume():
    signals, market, calendar = inputs()
    labels = fixed_labels(signals, market, calendar)
    row = labels.filter(pl.col("ts_code") == "A").row(0, named=True)
    assert row["label_target_date"] == "20260106"
    assert row["label_return"] is None and not row["label_valid"]
    assert row["label_status"] == "suspended"
    assert "label_return_rank" not in labels.columns


def test_cutoff_excluded_return_cannot_influence_rank_or_csz():
    data = pl.DataFrame(
        {
            "trade_date": ["20260105"] * 3,
            "trade_time": ["1445"] * 3,
            "label_return": [0.01, 0.02, -0.9],
            "label_valid": [True] * 3,
            "train": [True, True, False],
        }
    )
    left = transform_labels(data, reference=pl.col("train"), winsorize_tail=0.0)
    right = transform_labels(
        data.with_columns(pl.Series("label_return", [0.01, 0.02, 0.9])),
        reference=pl.col("train"),
        winsorize_tail=0.0,
    )
    assert left["label_return_rank"].to_list() == [0.0, 1.0, None]
    assert left.select("label_return_rank", "label_return_csz").equals(
        right.select("label_return_rank", "label_return_csz")
    )


def test_locked_capital_mark_to_market_and_delayed_exit():
    signals, market, calendar = inputs()
    result = run_backtest(
        signals,
        market,
        calendar,
        fixed_labels(signals, market, calendar),
        BacktestConfig(top_ns=(1,), transaction_cost_rate=0),
        as_of_date="20260108",
    )
    daily = result.frames["daily"]
    assert result.status == "done"
    assert daily["top1_net_value"].to_list() == pytest.approx([1.0, 1.0, 1.1, 1.1])
    assert result.frames["trades"]["exit_date"].to_list() == ["20260107"]
    assert result.frames["trades"]["exit_delayed"].to_list() == [True]
    assert result.frames["orders"].filter((pl.col("ts_code") == "B") & (pl.col("side") == "buy"))[
        "status"
    ].to_list() == ["unfilled"]
    assert daily["trade_date"].to_list() == calendar["trade_date"].to_list()


def test_missing_data_is_incomplete_not_confirmed_suspension():
    signals, market, calendar = inputs()
    market = market.with_columns(
        pl.when(pl.col("market_status") == "suspended")
        .then(pl.lit("missing_data"))
        .otherwise(pl.col("market_status"))
        .alias("market_status")
    )
    result = run_backtest(
        signals,
        market,
        calendar,
        None,
        BacktestConfig(top_ns=(1,), transaction_cost_rate=0),
        as_of_date="20260106",
    )
    assert result.status == "incomplete_market_data"
    assert result.frames["positions"].height == 2
    assert result.frames["trades"].is_empty()


def test_every_executed_side_pays_cost_and_future_quotes_cannot_change_prefix():
    signals, market, calendar = inputs()
    config = BacktestConfig(top_ns=(1,), transaction_cost_rate=0.01)
    full = run_backtest(signals, market, calendar, None, config, as_of_date="20260108")
    short = run_backtest(signals, market, calendar, None, config, as_of_date="20260106")
    assert (
        full.frames["daily"]
        .select("trade_date", "top1_net_value")
        .head(2)
        .equals(short.frames["daily"].select("trade_date", "top1_net_value"))
    )
    assert full.frames["orders"].filter(pl.col("status") == "filled")["fee"].sum() > 0.01
    assert full.frames["daily"]["top1_net_value"][-1] == pytest.approx(1.1 / 1.01 * 0.99)


def test_confirmed_suspension_with_stale_entry_price_is_not_a_training_label():
    from axonx.task.builtins.stock.data import apply_market_status

    signals, market, calendar = inputs()
    status = pl.DataFrame(
        {"trade_date": ["20260106"], "trade_time": ["1445"], "ts_code": ["B"], "market_status": ["suspended"]}
    )
    market = apply_market_status(market, status)
    labels = fixed_labels(signals, market, calendar)
    row = labels.filter(pl.col("ts_code") == "B").row(0, named=True)
    assert not row["label_valid"] and row["label_return"] is None
    assert row["label_status"] == "suspended"


def test_adjusted_units_preserve_value_across_split():
    signals, market, calendar = inputs()
    market = market.with_columns(
        pl.when((pl.col("ts_code") == "A") & (pl.col("trade_date") >= "20260107"))
        .then(pl.col("price") / 2)
        .otherwise(pl.col("price"))
        .alias("price"),
        pl.when((pl.col("ts_code") == "A") & (pl.col("trade_date") >= "20260107"))
        .then(2.0)
        .otherwise(pl.col("adjustment_factor"))
        .alias("adjustment_factor"),
    )
    result = run_backtest(
        signals, market, calendar, None, BacktestConfig(top_ns=(1,), transaction_cost_rate=0), as_of_date="20260108"
    )
    assert result.frames["daily"]["top1_net_value"].to_list() == pytest.approx([1.0, 1.0, 1.1, 1.1])
    assert result.frames["trades"]["realized_return"].to_list() == pytest.approx([0.1])


@pytest.mark.parametrize("bad_date", ["20260105x", "20260230", "2026015", None, "20260105"])
def test_invalid_calendar_is_rejected_by_labels_and_backtest(bad_date):
    signals, market, calendar = inputs()
    calendar = pl.concat([calendar, pl.DataFrame({"trade_date": [bad_date]}, schema={"trade_date": pl.String})])
    with pytest.raises(ValueError):
        fixed_labels(signals, market, calendar)
    with pytest.raises(ValueError):
        run_backtest(signals, market, calendar, None, BacktestConfig(top_ns=(1,)), as_of_date="20260108")


def test_index_diagnostics_ignore_outside_scores_and_returns():
    signals, market, calendar = inputs()
    first = signals.head(1).with_columns(pl.lit(0.5).alias("index_weight_test"))
    signals = pl.concat(
        [
            first,
            first.with_columns(pl.lit("D").alias("ts_code"), pl.lit(1.0).alias("pred")),
            first.with_columns(
                pl.lit("C").alias("ts_code"), pl.lit(10.0).alias("pred"), pl.lit(0.0).alias("index_weight_test")
            ),
        ]
    )
    labels = pl.DataFrame(
        {
            "trade_date": ["20260105"] * 3,
            "trade_time": ["1445"] * 3,
            "ts_code": ["A", "D", "C"],
            "label_target_date": ["20260106"] * 3,
            "label_valid": [True] * 3,
            "label_return": [0.1, 0.05, 0.2],
        }
    )
    config = BacktestConfig(top_ns=(1,), index_codes=("test",))
    before = run_backtest(signals, market, calendar, labels, config, as_of_date="20260108")
    after = run_backtest(
        signals.with_columns(pl.when(pl.col("ts_code") == "C").then(-10.0).otherwise(pl.col("pred")).alias("pred")),
        market,
        calendar,
        labels.with_columns(
            pl.when(pl.col("ts_code") == "C").then(-0.9).otherwise(pl.col("label_return")).alias("label_return")
        ),
        config,
        as_of_date="20260108",
    )
    assert before.frames["targets"]["ts_code"].to_list() == ["A", "D"]
    columns = ["ic", "rank_ic", "top1_ndcg"]
    assert before.frames["daily"].select(columns).equals(after.frames["daily"].select(columns))
    assert before.frames["daily"]["top1_ndcg"][0] == pytest.approx(1.0)


def test_unfilled_top_target_is_not_replaced():
    signals, market, calendar = inputs()
    first = signals.head(1)
    signals = pl.concat([first, first.with_columns(pl.lit("B").alias("ts_code"), pl.lit(1.0).alias("pred"))])
    first_quote = market.filter((pl.col("trade_date") == "20260105") & (pl.col("ts_code") == "A"))
    market = pl.concat(
        [
            market.with_columns(
                pl.when(pl.col("ts_code") == "A").then(False).otherwise(pl.col("can_buy")).alias("can_buy")
            ),
            first_quote.with_columns(pl.lit("B").alias("ts_code")),
        ]
    )
    result = run_backtest(
        signals, market, calendar, None, BacktestConfig(top_ns=(1,), transaction_cost_rate=0), as_of_date="20260108"
    )
    assert result.frames["positions"].is_empty()
    assert result.frames["trades"].is_empty()
    assert result.frames["orders"]["ts_code"].to_list() == ["A"]
    assert result.frames["daily"]["top1_net_value"].to_list() == [1.0] * 4


def test_empty_labels_keep_portfolio_and_nullable_diagnostics():
    signals, market, calendar = inputs()
    labels = fixed_labels(signals, market, calendar).clear()
    config = BacktestConfig(top_ns=(1, 3), transaction_cost_rate=0)
    result = run_backtest(signals, market, calendar, labels, config, as_of_date="20260108")
    without = run_backtest(signals, market, calendar, None, config, as_of_date="20260108")
    assert (
        result.frames["daily"]
        .select("top1_net_value", "top3_net_value")
        .equals(without.frames["daily"].select("top1_net_value", "top3_net_value"))
    )
    assert result.frames["daily"]["ic"].null_count() == 4
    assert result.frames["daily"]["top3_ndcg"].null_count() == 4
    assert result.frames["targets"]["label_return"].null_count() == signals.height


@pytest.mark.parametrize("bad_time", ["2400", "1260", "945", "15:00", None])
def test_invalid_signal_time_is_rejected(bad_time):
    signals, market, calendar = inputs()
    signals = signals.with_columns(pl.lit(bad_time, dtype=pl.String).alias("trade_time"))
    with pytest.raises(ValueError):
        fixed_labels(signals, market, calendar)
    with pytest.raises(ValueError):
        run_backtest(signals, market, calendar, None, BacktestConfig(top_ns=(1,)), as_of_date="20260108")


@pytest.mark.parametrize("buy,sell", [(0.0005, 0.0015), (0.0, 0.0015), (None, 0.0015)])
def test_asymmetric_fees_preserve_cash_and_charge_only_executed_sides(buy, sell):
    signals, market, calendar = inputs()
    config = BacktestConfig(top_ns=(1,), transaction_cost_rate=0.01, buy_cost_rate=buy, sell_cost_rate=sell)
    result = run_backtest(signals, market, calendar, None, config, as_of_date="20260108")
    rate = 0.01 if buy is None else buy
    orders = result.frames["orders"]
    for row in orders.filter(pl.col("status") == "filled").iter_rows(named=True):
        expected = rate if row["side"] == "buy" else sell
        assert row["fee"] == pytest.approx(row["notional"] * expected)
    assert orders.filter(pl.col("status") != "filled")["fee"].sum() == 0
    assert result.frames["daily"]["top1_net_value"][-1] == pytest.approx(1.1 / (1 + rate) * (1 - sell))


@pytest.mark.parametrize("buy,sell", [(-0.01, None), (None, 1.0)])
def test_invalid_side_cost_is_rejected(buy, sell):
    signals, market, calendar = inputs()
    with pytest.raises(ValueError, match="buy_cost_rate and sell_cost_rate"):
        run_backtest(
            signals,
            market,
            calendar,
            None,
            BacktestConfig(top_ns=(1,), buy_cost_rate=buy, sell_cost_rate=sell),
            as_of_date="20260108",
        )
