"""Reuse the base Alpha158 analysis implementation."""

from axonx_alpha158.analysis import (
    FactorAnalysisInputParams,
    FactorAnalysisOutputParams,
    FactorAnalysisTask as BaseTask,
)

__all__ = ["FactorAnalysisInputParams", "FactorAnalysisOutputParams", "FactorAnalysisTask"]


class FactorAnalysisTask(BaseTask):
    pass
