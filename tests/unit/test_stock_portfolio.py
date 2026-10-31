"""Portfolio identities, frozen target construction and independent execution scenarios."""

import polars as pl
import pytest
from pydantic import ValidationError

from axonx.task.builtins.stock.backtest import BaseStockBacktestTask
from axonx.task.builtins.stock.portfolio import (
    BaseStockPortfolioTask,
    PortfolioReader,
    portfolio_targets,
    prepare_portfolio_signals,
)
from axonx.task.models.artifacts import task_protocol
from axonx.task.models.identity import TaskType
from axonx.task.models.params import BasePortfolioOutputParams
from axonx.task.runtime.executor import TaskExecutor
from axonx.task.storage.files import file_revision


def test_identity_is_readable_extensible_and_unique_by_content():
    output = BasePortfolioOutputParams(
        portfolios=[
            {"portfolio_id": {"top_n": 5}, "artifacts": {}},
            {"portfolio_id": {"top_n": 5, "strategy": {"kind": "rank_retention"}}, "artifacts": {}},
        ],
        protocol=task_protocol(TaskType.PORTFOLIO),
    )
    assert output.model_dump()["portfolios"][0]["portfolio_id"] == {"top_n": 5}
    with pytest.raises(ValidationError, match="unique"):
        BasePortfolioOutputParams(
            portfolios=[
                {"portfolio_id": {"top_n": 5, "strategy": "hold"}, "artifacts": {}},
                {"portfolio_id": {"strategy": "hold", "top_n": 5}, "artifacts": {}},
            ],
            protocol=task_protocol(TaskType.PORTFOLIO),
        )
    with pytest.raises(ValidationError):
        BasePortfolioOutputParams(
            portfolios=[{"portfolio_id": {"weight": float("nan")}, "artifacts": {}}],
            protocol=task_protocol(TaskType.PORTFOLIO),
        )


def test_portfolio_freezes_targets_and_backtests_reuse_them_with_different_costs(tmp_path):
    signals = pl.DataFrame(
        {
            "trade_date": ["20240102"] * 3,
            "trade_time": ["1445"] * 3,
            "ts_code": ["A", "B", "C"],
            "pred": [3.0, 2.0, 1.0],
            "is_model_candidate": [True] * 3,
            "is_buyable_at_signal": [False, True, True],
            "signal_price": [10.0] * 3,
            "signal_adjustment_factor": [1.0] * 3,
        }
    )
    source = tmp_path / "predictions.parquet"
    signals.write_parquet(source)
    market = signals.select("trade_date", "trade_time", "ts_code").with_columns(
        pl.lit(10.0).alias("price"),
        pl.lit(1.0).alias("adjustment_factor"),
        pl.lit("quoted").alias("market_status"),
        pl.lit(True).alias("can_buy"),
        pl.lit(True).alias("can_sell"),
    )
    market.write_parquet(tmp_path / "market.parquet")
    pl.DataFrame({"trade_date": ["20240102"]}).write_parquet(tmp_path / "calendar.parquet")
    portfolio = BaseStockPortfolioTask(
        {
            "input_file": source,
            "top_ns": [1, 2],
            "strategies": [{"kind": "fixed_expiry", "holding_days": 2}, {"kind": "rank_retention"}],
        },
        workspace_path=tmp_path,
        reg_name="selection",
    )
    executor = TaskExecutor()
    executor.execute(portfolio)
    assert portfolio.output_params.protocol["input_revisions"] == {"predictions": file_revision(source)}
    identities = [item.portfolio_id for item in portfolio.output_params.portfolios]
    assert [item["top_n"] for item in identities] == [1, 2, 1, 2]
    assert [item["strategy"]["kind"] for item in identities] == [
        "fixed_expiry",
        "fixed_expiry",
        "rank_retention",
        "rank_retention",
    ]
    for plan in portfolio.output_params.portfolios:
        assert plan.artifacts == {"rankings": "rankings"}
        frozen = PortfolioReader(portfolio, portfolio.task_id).signals(plan)
        assert frozen.height == signals.height
        assert "target_weight" not in frozen.columns
        targets = portfolio_targets(frozen, plan.portfolio_id["top_n"])
        assert targets["ts_code"].to_list() == ["B", "C"][: plan.portfolio_id["top_n"]]
    assert [p.name for p in portfolio.task_dir.glob("*.parquet")] == ["rankings.parquet"]
    assert not (portfolio.task_dir / "portfolios").exists()
    assert all("buy_cost_rate" not in item for item in identities)
    top1 = portfolio.output_params.portfolios[0]
    targets = portfolio_targets(PortfolioReader(portfolio, portfolio.task_id).signals(top1), 1)
    assert targets["ts_code"].to_list() == ["B"]
    assert targets["target_weight"].to_list() == [1.0]
    reports = []
    for fee in [0.0, 0.01]:
        task = BaseStockBacktestTask(
            {
                "upstream_task_ids": [portfolio.task_id],
                "portfolio_ids": [identities[0]],
                "market_file": "market.parquet",
                "calendar_file": "calendar.parquet",
                "buy_cost_rate": fee,
                "sell_cost_rate": 0,
            },
            workspace_path=tmp_path,
            reg_name="execution",
        )
        executor.execute(task)
        assert [item.portfolio_id for item in task.output_params.portfolios] == [identities[0]]
        report = task.output_params.portfolios[0]
        orders = pl.read_parquet(task.artifact_path(report.artifacts["orders"]))
        assert orders["ts_code"].to_list() == ["B"]
        reports.append(pl.read_parquet(task.artifact_path(report.artifacts["daily"]))["top1_net_value"][0])
    assert reports[0] == 1.0
    assert reports[1] < reports[0]
    assert "signals" not in report.artifacts
    signals.with_columns(pl.col("pred").reverse()).write_parquet(source)
    with pytest.raises(ValueError, match="Predictions changed"):
        PortfolioReader(portfolio, portfolio.task_id)
    with pytest.raises(ValidationError):
        BaseStockBacktestTask({"top_ns": [5]}, workspace_path=tmp_path, reg_name="execution")


def test_signal_ranking_is_independent_of_future_labels():
    frame = pl.DataFrame(
        {
            "trade_date": ["20240102"] * 2,
            "trade_time": ["1445"] * 2,
            "ts_code": ["B", "A"],
            "pred": [1.0, 1.0],
            "is_model_candidate": [True, True],
            "is_buyable_at_signal": [True, True],
            "label_return": [100.0, -100.0],
        }
    )
    left = prepare_portfolio_signals(frame).sort("target_rank")
    right = prepare_portfolio_signals(frame.with_columns(-pl.col("label_return"))).sort("target_rank")
    assert left.select("ts_code", "target_rank").equals(right.select("ts_code", "target_rank"))
    assert left["ts_code"].to_list() == ["A", "B"]
