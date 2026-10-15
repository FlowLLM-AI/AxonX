"""Standard contract for backtest Tasks."""

from abc import ABC
from typing import Any

from pydantic import Field, field_validator, model_validator

from ...enums import TaskType
from ..core import BaseInputParams, BaseOutputParams, BaseTask
from ..schemas.protocol import validate_protocol
from ..schemas.reports import BacktestBenchmark, BacktestDimensions, BacktestUniverse, BacktestUniverseReport


class BaseBacktestOutputParams(BaseOutputParams):
    default_universe: str
    universes: dict[str, BacktestUniverseReport] = Field(min_length=1)
    protocol: dict[str, Any]

    @model_validator(mode="after")
    def validate_universes(self):
        if self.default_universe not in self.universes:
            raise ValueError("default_universe must reference a published report")
        for report in self.universes.values():
            if not {"daily", "summary"} <= report.artifacts.keys():
                raise ValueError("Every universe requires daily and summary artifacts")
            if set(report.artifacts.values()) - self.artifacts.keys():
                raise ValueError("Universe references an unregistered artifact")
        return self

    @field_validator("protocol")
    @classmethod
    def validate_backtest_protocol(cls, value):
        return validate_protocol(value, TaskType.BACKTEST)


class BaseBacktestTask(BaseTask, ABC):
    """Evaluate predictions and publish standard daily and summary artifacts."""

    task_type = TaskType.BACKTEST
    input_cls = BaseInputParams
    output_cls = BaseBacktestOutputParams


__all__ = [
    "BacktestBenchmark",
    "BacktestDimensions",
    "BacktestUniverse",
    "BacktestUniverseReport",
    "BaseBacktestOutputParams",
    "BaseBacktestTask",
]
