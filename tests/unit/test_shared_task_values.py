"""Shared value contracts retain Task defaults and one execution result."""

import pytest
from pydantic import ValidationError

from axonx.task.builtins.stock import StockBacktestInput
from axonx.task.builtins.stock.settings import PortfolioSettings
from axonx.task.runtime.executor import TaskExecutor
from axonx.task.storage.workspace import read_task_metadata, task_path


def test_executor_returns_persisted_metadata_without_cli_protocol(tmp_path):
    status = TaskExecutor(tmp_path).execute("demo", {"x": 2, "y": 3, "task_name": "fixed"})
    assert status == read_task_metadata(task_path(tmp_path, status.task_id), status.task_id)
    assert status.output_params["result"] == 5
    assert status.state == "succeeded"


def test_framework_portfolio_defaults_and_engine_conversion():
    params = StockBacktestInput()
    assert isinstance(params, PortfolioSettings)
    assert params.holding_days == 1
    assert params.top_ns == [1, 2, 3, 5, 10, 20, 30]
    assert not params.missing_market_as_suspension
    assert params.engine_config(holding_days=None).holding_days is None
    assert StockBacktestInput(top_ns=[50, 2, 2]).engine_config(holding_days=3).top_ns == (2, 50)
    with pytest.raises(ValidationError, match="positive"):
        StockBacktestInput(top_ns=[0])
