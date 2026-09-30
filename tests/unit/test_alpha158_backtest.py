"""Alpha158 backtest contract and calculation tests."""

import polars as pl
import pytest

from axonx.task.contracts import BaseBacktestTask
from axonx_alpha158.backtest import (
    Alpha158BacktestInputParams,
    Alpha158BacktestTask,
)
from axonx_alpha158.internal.backtest import BacktestConfig, TOP_NS, run_backtest


def test_alpha158_backtest_implements_the_standard_contract():
    assert issubclass(Alpha158BacktestTask, BaseBacktestTask)
    params = Alpha158BacktestInputParams(index_codes=[" HS300 ", "hs300"])
    assert params.index_codes == ["hs300"]


def test_backtest_engine_builds_standard_artifacts():
    frame = pl.DataFrame(
        {
            "trade_date": ["20260105"] * 3 + ["20260106"] * 3,
            "ts_code": ["A", "B", "C"] * 2,
            "name": ["甲", "乙", "丙"] * 2,
            "pred": [3.0, 2.0, 1.0, 1.0, 3.0, 2.0],
            "actual_return": [0.03, 0.02, 0.01, -0.01, 0.01, 0.02],
            "label_valid": [True] * 6,
            "is_buyable": [True] * 6,
            "entry_is_buyable": [True] * 6,
            "exit_is_sellable": [True] * 6,
            "exit_delayed": [False] * 6,
            "entry_date": ["20260106"] * 3 + ["20260107"] * 3,
            "exit_date": ["20260107"] * 3 + ["20260108"] * 3,
            "index_weight_hs300": [0.4, 0.3, 0.3] * 2,
        },
    )
    result = run_backtest(
        frame,
        ("index_weight_hs300",),
        BacktestConfig(
            transaction_cost_rate=0.002,
            annual_risk_free_rate=0.012,
            annualization_days=252,
            minimum_index_weight_coverage=0.9,
            index_codes=("hs300",),
        ),
    )

    assert result.daily.height == 4
    assert result.summary["period_type"].unique().sort().to_list() == [
        "month",
        "overall",
        "quarter",
        "year",
    ]
    assert result.benchmark_keys == ("universe", "hs300")
    assert result.daily.filter(pl.col("top30_holdings").is_not_null())["top30_holdings"].list.len().to_list() == [3, 3]
    for top_n in TOP_NS:
        assert f"top{top_n}_net_return" in result.daily.columns
        assert f"top{top_n}_net_cumulative_return" in result.summary.columns
        daily_gross = result.daily[f"top{top_n}_gross_return"]
        expected_gross = (daily_gross + 1).product() - 1
        overall = result.summary.filter(pl.col("period_type") == "overall").row(
            0,
            named=True,
        )
        assert overall[f"top{top_n}_gross_cumulative_return"] == expected_gross


def test_unfilled_top_pick_stays_cash_without_replacing_it():
    frame = pl.DataFrame(
        {
            "trade_date": ["20260105", "20260105"],
            "entry_date": ["20260106"] * 2,
            "exit_date": ["20260107"] * 2,
            "ts_code": ["A", "B"],
            "name": ["甲", "乙"],
            "pred": [2.0, 1.0],
            "actual_return": [0.1, 0.2],
            "label_valid": [True, True],
            "is_buyable": [True, True],
            "entry_is_buyable": [False, True],
            "exit_is_sellable": [True, True],
            "exit_delayed": [False, False],
        },
    )
    result = run_backtest(
        frame,
        (),
        BacktestConfig(0.0, 0.012, 252, 0.9, ()),
    )
    assert result.daily["top1_gross_return"].sum() == 0
    assert result.daily["top1_turnover"].sum() == 0
    assert abs(result.daily["top2_gross_return"].sum() - 0.1) < 1e-12


def test_delayed_exit_keeps_capital_locked_until_actual_exit():
    frame = pl.DataFrame(
        {
            "trade_date": ["20260105", "20260106"],
            "entry_date": ["20260106", "20260107"],
            "exit_date": ["20260109", "20260108"],
            "ts_code": ["A", "B"],
            "name": ["甲", "乙"],
            "pred": [2.0, 3.0],
            "actual_return": [0.2, 0.1],
            "label_valid": [True, True],
            "exit_delayed": [True, False],
            "is_buyable": [True, True],
            "entry_is_buyable": [True, True],
            "exit_is_sellable": [False, True],
        },
    )
    result = run_backtest(frame, (), BacktestConfig(0.0, 0.012, 252, 0.9, ()))
    daily = result.daily.sort("trade_date")
    assert daily["trade_date"].to_list() == ["20260105", "20260106", "20260107", "20260108", "20260109"]
    assert daily["top1_gross_return"].to_list() == [0.0, 0.0, 0.0, 0.0, 0.2]
    assert daily["top1_delayed_open_positions"].to_list() == [0, 1, 1, 1, 0]
    assert daily["top1_delayed_exits"].to_list() == [0, 0, 0, 0, 1]
    assert daily["top1_exits"].sum() == 1


def test_unresolved_exit_is_reported_as_open_position():
    frame = pl.DataFrame(
        {
            "trade_date": ["20260105"],
            "entry_date": ["20260106"],
            "exit_date": [None],
            "ts_code": ["A"],
            "name": ["甲"],
            "pred": [1.0],
            "actual_return": [None],
            "label_valid": [False],
            "exit_delayed": [True],
            "is_buyable": [True],
            "entry_is_buyable": [True],
            "exit_is_sellable": [False],
        },
    )
    result = run_backtest(frame, (), BacktestConfig(0.0, 0.012, 252, 0.9, ()))
    assert result.daily["top1_unsettled_positions"].to_list() == [0, 1]
    assert result.daily["top1_gross_return"].sum() == 0


def test_known_exit_requires_valid_return_for_bought_position():
    frame = pl.DataFrame(
        {
            "trade_date": ["20260105"],
            "entry_date": ["20260106"],
            "exit_date": ["20260108"],
            "ts_code": ["A"],
            "name": ["甲"],
            "pred": [1.0],
            "actual_return": [None],
            "label_valid": [False],
            "exit_delayed": [True],
            "is_buyable": [True],
            "entry_is_buyable": [True],
            "exit_is_sellable": [False],
        },
    )
    with pytest.raises(ValueError, match="已知退出日期的买入样本缺少有效收益"):
        run_backtest(frame, (), BacktestConfig(0.0, 0.012, 252, 0.9, ()))


def test_close_labels_fund_same_day_rebalance_after_next_close_exit():
    """次日收盘卖出后，用释放的资金买入当日信号，遵循 T+1。"""
    from axonx_alpha158.internal.etl_pipeline import calculate_labels

    quotes = pl.DataFrame(
        {
            "ts_code": ["A"] * 3,
            "trade_date": ["20260921", "20260922", "20260923"],
            "close": [10.0, 11.0, 12.1],
            "_close": [10.0, 11.0, 12.1],
            "up_limit": [20.0] * 3,
            "down_limit": [1.0] * 3,
            "_has_market_data": [True] * 3,
            "_has_valid_limits": [True] * 3,
            "is_st": [False] * 3,
            "is_delisting": [False] * 3,
        },
    )
    predictions = (
        calculate_labels(quotes, 0.025)
        .head(2)
        .with_columns(
            pl.col("label_1d").alias("actual_return"),
            pl.col("label_1d_is_valid").alias("label_valid"),
            pl.lit(1.0).alias("pred"),
            pl.lit(True).alias("is_buyable"),
            pl.lit("甲").alias("name"),
        )
    )
    result = run_backtest(predictions, (), BacktestConfig(0.0, 0.012, 252, 0.9, ()))
    daily = result.daily.sort("trade_date")
    assert daily["trade_date"].to_list() == quotes["trade_date"].to_list()
    assert daily["top1_gross_return"].to_list() == pytest.approx([0.0, 0.1, 0.1])
    assert daily["top1_open_positions"].to_list() == [1, 1, 0]
    assert daily["top1_exits"].to_list() == [0, 1, 1]
