"""Reuse the base Alpha158 analysis implementation."""

from axonx_alpha158.analysis import (
    FactorAnalysisInputParams,
    FactorAnalysisOutputParams,
    FactorAnalysisTask as BaseTask,
)

__all__ = ["FactorAnalysisInputParams", "FactorAnalysisOutputParams", "FactorAnalysisTask"]


class FactorAnalysisTask(BaseTask):
    """Analyze upstream Alpha158 and context factors using the shared diagnostics.

    Reads the ETL feature and label artifacts and writes factor analysis results
    through the baseline analysis lifecycle, without altering training samples.
    """
