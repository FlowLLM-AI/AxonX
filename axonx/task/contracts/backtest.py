"""Standard contract for backtest Tasks."""

from abc import ABC
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ...enums import TaskType
from ..core import BaseInputParams, BaseOutputParams, BaseTask
from ..protocol import validate_protocol


class BacktestBenchmark(BaseModel):
    """One benchmark series exposed by a backtest artifact."""

    key: str
    label: str


class BacktestDimensions(BaseModel):
    """Dimensions needed to render standard backtest artifacts."""

    top_ns: list[int]
    holding_detail_top_n: int
    benchmarks: list[BacktestBenchmark]


class BacktestUniverse(BaseModel):
    """Plugin-owned selection definition; the framework owns result publication."""

    model_config = ConfigDict(extra="forbid")
    key: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    label: str = Field(min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)


class BacktestUniverseReport(BaseModel):
    """One independent portfolio report; artifact names reference the Task registry."""

    model_config = ConfigDict(extra="forbid")
    label: str
    parameters: dict[str, Any]
    dimensions: BacktestDimensions
    date_range: dict[str, str]
    days: int
    evaluation_status: str
    artifacts: dict[str, str]


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
