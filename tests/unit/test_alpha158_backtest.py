"""Alpha158 backtest contract and calculation tests."""

import polars as pl

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
            "entry_date": ["20260106"] * 3 + ["20260107"] * 3,
            "exit_date": ["20260107"] * 3 + ["20260108"] * 3,
            "index_weight_hs300": [0.4, 0.3, 0.3] * 2,
        }
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

    assert result.daily.height == 2
    assert result.summary["period_type"].unique().sort().to_list() == [
        "month",
        "overall",
        "quarter",
        "year",
    ]
    assert result.benchmark_keys == ("universe", "hs300")
    assert result.daily["top30_holdings"].list.len().to_list() == [3, 3]
    for top_n in TOP_NS:
        assert f"top{top_n}_net_return" in result.daily.columns
        assert f"top{top_n}_net_cumulative_return" in result.summary.columns
        daily_gross = result.daily[f"top{top_n}_gross_return"]
        expected_gross = (daily_gross + 1).product() - 1
        overall = result.summary.filter(pl.col("period_type") == "overall").row(
            0, named=True
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
        }
    )
    result = run_backtest(
        frame,
        (),
        BacktestConfig(0.002, 0.012, 252, 0.9, ()),
    )
    assert result.daily["top1_gross_return"].item() == 0
    assert result.daily["top1_turnover"].item() == 0
    assert result.daily["top2_gross_return"].item() == 0.1
