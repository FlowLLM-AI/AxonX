"""Shared value contracts retain Task defaults and one execution result."""

import pytest
from pydantic import ValidationError

from axonx.enums import TaskType
from axonx.task.artifact import ArtifactRecord
from axonx.task.builtins.stock import StockBacktestInput
from axonx.task.builtins.stock.settings import PortfolioSettings
from axonx.task.contracts import OnlineArtifact
from axonx.task.runtime.executor import TaskExecution
from axonx.task.storage.workspace import TaskMetadata


def test_execution_output_is_the_status_output_and_old_constructor_remains_supported():
    status = TaskMetadata(version=1, task_id="base#demo#fixed", run_id="run", task_type=TaskType.BASE)
    status.output_params = {"answer": [42]}
    result = TaskExecution(status=status)
    assert result.output is status.output_params
    assert TaskExecution({"answer": [42]}, status).output is status.output_params
    status.output_params = {"answer": [43]}
    assert result.output == {"answer": [43]}
    with pytest.raises(ValueError, match="differs"):
        TaskExecution({"answer": [42]}, status)


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


def test_online_artifact_is_the_shared_record():
    assert OnlineArtifact is ArtifactRecord
