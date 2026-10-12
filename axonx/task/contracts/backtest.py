"""Standard contract for backtest Tasks."""

from abc import ABC
from typing import Any

from pydantic import BaseModel, field_validator

from ...enums import TaskType
from ..protocol import validate_protocol
from ..core import BaseInputParams, BaseOutputParams, BaseTask


class BacktestBenchmark(BaseModel):
    """One benchmark series exposed by a backtest artifact."""

    key: str
    label: str


class BacktestDimensions(BaseModel):
    """Dimensions needed to render standard backtest artifacts."""

    top_ns: list[int]
    holding_detail_top_n: int
    benchmarks: list[BacktestBenchmark]


class BaseBacktestInputParams(BaseInputParams):
    pass


class BaseBacktestOutputParams(BaseOutputParams):
    dimensions: BacktestDimensions
    protocol: dict[str, Any]
    date_range: dict[str, str]
    days: int

    @field_validator("protocol")
    @classmethod
    def validate_backtest_protocol(cls, value):
        return validate_protocol(value, TaskType.BACKTEST)


class BaseBacktestTask(BaseTask, ABC):
    """Evaluate predictions and publish standard daily and summary artifacts."""

    task_type = TaskType.BACKTEST
    input_cls = BaseBacktestInputParams
    output_cls = BaseBacktestOutputParams
