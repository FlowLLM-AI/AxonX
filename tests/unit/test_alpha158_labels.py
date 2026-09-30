"""验证收盘标签的复权口径、交易日对齐及不可交易样本。"""

import polars as pl
import pytest

from axonx_alpha158.internal.etl_pipeline import LABEL_OUTPUTS, calculate_labels


def market_frame(prices, *, missing=(), limit_down=(), limit_up=()):
    """连续交易日面板；开盘价刻意不同于收盘价，避免误用旧收益口径。"""
    return pl.DataFrame(
        {
            "ts_code": ["A"] * len(prices),
            "trade_date": [f"202609{day:02d}" for day in range(21, 21 + len(prices))],
            "open": [5.0] * len(prices),
            "_open": [5.0] * len(prices),
            "close": prices,
            "_close": prices,
            "up_limit": [price if i in limit_up else 50.0 for i, price in enumerate(prices)],
            "down_limit": [price if i in limit_down else 1.0 for i, price in enumerate(prices)],
            "_has_market_data": [i not in missing for i in range(len(prices))],
            "_has_valid_limits": [True] * len(prices),
            "is_st": [False] * len(prices),
            "is_delisting": [False] * len(prices),
        },
    )


def test_label_uses_signal_close_and_next_market_close_with_adjustment():
    """验证复权收益以当天收盘入场，并在下一交易日收盘退出。"""
    # 第二天原始价格因除权减半，复权价格仍上涨 10%。
    frame = market_frame([10.0, 5.5, 6.0]).with_columns(
        pl.Series("_close", [10.0, 11.0, 12.0]),
    )
    output = calculate_labels(frame, 0.025)
    first = output.row(0, named=True)
    assert LABEL_OUTPUTS == ("label_1d", "label_1d_csz", "label_1d_rank", "label_1d_is_valid")
    assert first["label_1d"] == pytest.approx(0.1)
    assert (first["entry_date"], first["exit_date"]) == ("20260921", "20260922")
    assert first["entry_is_buyable"] and first["exit_is_sellable"]
    assert not first["exit_delayed"]
    assert first["label_1d_rank"] == 1.0
    assert output["label_1d_is_valid"].to_list() == [True, True, False]
    assert not output.row(-1, named=True)["exit_delayed"]


@pytest.mark.parametrize("reason", ["suspension", "limit_down"])
def test_delayed_exit_uses_first_sellable_close_and_excludes_strict_labels(reason):
    """停牌或跌停时延迟退出，不把延迟收益纳入严格一天标签。"""
    frame = market_frame(
        [10.0, 11.0, 12.0],
        **{
            "missing" if reason == "suspension" else "limit_down": (1,),
        },
    )
    first = calculate_labels(frame, 0.025).row(0, named=True)
    assert first["exit_date"] == "20260923"
    assert first["label_1d"] == pytest.approx(0.2)
    assert first["exit_delayed"] and first["label_1d_is_valid"]
    assert not first["exit_is_sellable"]
    assert first["label_1d_rank"] is None
    assert first["label_1d_csz"] is None


def test_suspended_entry_is_invalid_even_if_stale_close_is_present():
    """停牌时即使残留旧收盘价，也不能产生有效买入或收益。"""
    first = calculate_labels(market_frame([10.0, 11.0], missing=(0,)), 0.025).row(0, named=True)
    assert not first["entry_is_buyable"]
    assert not first["label_1d_is_valid"]
    assert first["label_1d"] is None


def test_limit_up_entry_remains_a_research_label_but_cannot_be_bought():
    """涨停样本保留研究收益，但日线代理判定不可买。"""
    first = calculate_labels(market_frame([10.0, 11.0], limit_up=(0,)), 0.025).row(0, named=True)
    assert not first["entry_is_buyable"]
    assert first["label_1d"] == pytest.approx(0.1)
    assert first["label_1d_is_valid"]


def test_unresolved_exit_does_not_invent_a_next_day_fill():
    """样本尾部无法退出时保留未结清状态，不虚构成交。"""
    first = calculate_labels(market_frame([10.0, 11.0], limit_down=(1,)), 0.025).row(0, named=True)
    assert first["entry_is_buyable"]
    assert first["exit_date"] is None
    assert first["exit_delayed"]
    assert not first["label_1d_is_valid"]
    assert first["label_1d_rank"] is None


def test_close_shifts_and_cross_sectional_transforms_stay_within_each_symbol():
    """未来价格不跨股票串接，排名和标准化按日横截面计算。"""
    a = market_frame([10.0, 11.0])
    b = market_frame([20.0, 18.0]).with_columns(pl.lit("B").alias("ts_code"))
    output = calculate_labels(pl.concat([a, b]), 0.0)
    first = output.filter(pl.col("trade_date") == "20260921").sort("ts_code")
    assert first["label_1d"].to_list() == pytest.approx([0.1, -0.1])
    assert first["label_1d_rank"].to_list() == [1.0, 0.5]
    assert first["label_1d_csz"].to_list() == pytest.approx([1.0, -1.0])
    assert output.filter(pl.col("trade_date") == "20260922")["label_1d_is_valid"].to_list() == [False, False]
