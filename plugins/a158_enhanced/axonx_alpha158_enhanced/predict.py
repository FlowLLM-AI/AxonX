"""Reuse the base Alpha158 predict implementation."""

from axonx_alpha158.predict import (
    LgbmPredictInputParams,
    LgbmPredictOutputParams,
    LgbmPredictTask as BaseTask,
)

__all__ = ["LgbmPredictInputParams", "LgbmPredictOutputParams", "LgbmPredictTask"]


class LgbmPredictTask(BaseTask):
    pass
