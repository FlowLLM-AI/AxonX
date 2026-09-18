"""Common contract for training tasks."""

from abc import ABC
from math import isfinite
from typing import Any

from pydantic import BaseModel, Field, model_validator

from ...enums import TaskType
from ..base import BaseInputParams, BaseOutputParams, BaseTask


class BaseTrainInputParams(BaseInputParams):
    pass


class TrainingCurve(BaseModel):
    """Aligned training history for one chart with up to two y-axis ranges.

    Each ``x[i]`` labels the same training point in every series. Producers
    may use iteration numbers, timestamps, or another ordered string label.
    ``y_left`` contains series with comparable units and numeric ranges on
    the primary axis. Use optional ``y_right`` only for a second group that
    needs an independent scale; do not mix substantially different scales
    within either group or add a third group.

    Every series has exactly ``len(x)`` finite samples, and names are unique
    across the two groups. A populated curve requires at least one left-axis
    series. Empty ``x`` and empty groups mean no curve data is available.
    """

    x: list[str] = Field(
        default_factory=list,
        description="Ordered labels shared by every series, e.g. iterations or timestamps.",
    )
    y_left: dict[str, list[float]] = Field(
        default_factory=dict,
        description="Named series sharing the primary left y-axis value range.",
    )
    y_right: dict[str, list[float]] = Field(
        default_factory=dict,
        description="Named series sharing an optional second value range on the right y-axis.",
    )

    @model_validator(mode="after")
    def validate_series(self):
        if not self.x and (self.y_left or self.y_right):
            raise ValueError("Training curve series require x-axis points")
        if self.x and not self.y_left:
            raise ValueError("A populated training curve requires a left-axis series")
        if self.y_right and not self.y_left:
            raise ValueError("Right-axis series require a left-axis series")
        if self.y_left.keys() & self.y_right.keys():
            raise ValueError("Training curve series names must be unique across axes")
        for name, values in (*self.y_left.items(), *self.y_right.items()):
            if len(values) != len(self.x):
                raise ValueError(f"Training curve series {name!r} must match the x-axis length")
            if not all(isfinite(value) for value in values):
                raise ValueError(f"Training curve series {name!r} must contain finite values")
        return self


class BaseTrainOutputParams(BaseOutputParams):
    model_file: str
    train_rows: int
    model_name: str | None = None
    feature_columns: list[str] = Field(default_factory=list)
    target_columns: list[str] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)
    training_curve: TrainingCurve = Field(
        default_factory=TrainingCurve,
        description="Optional aligned training history with up to two value ranges, one per y-axis.",
    )


class BaseTrainTask(BaseTask, ABC):
    """Train a model using a completed ETL dataset.

    The result includes the saved model, training metrics, and optional curves.
    """

    task_type = TaskType.TRAIN
    input_cls = BaseTrainInputParams
    output_cls = BaseTrainOutputParams
