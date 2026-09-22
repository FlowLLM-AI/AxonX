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
