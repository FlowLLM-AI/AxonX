"""Reuse the base Alpha158 predict implementation."""

from axonx_qlib_a158.predict import (
    LgbmPredictInputParams,
    LgbmPredictOutputParams,
    LgbmPredictTask as BaseTask,
)

__all__ = ["LgbmPredictInputParams", "LgbmPredictOutputParams", "LgbmPredictTask"]


class LgbmPredictTask(BaseTask):
    """Predict the full stock cross section using a factor-layer training Task.

    Reuses the associated ETL dataset and recorded model feature order. Writes
    cutoff-safe prediction artifacts and summary statistics through Alpha158.
    """
