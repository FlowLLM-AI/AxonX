"""Reuse Alpha158 portfolio accounting with factor-enhanced predictions."""

from axonx_alpha158.backtest import Alpha158BacktestInputParams, Alpha158BacktestTask as BaseTask

__all__ = ["Alpha158BacktestInputParams", "Alpha158BacktestTask"]


class Alpha158BacktestTask(BaseTask):
    """Evaluate factor predictions using the unchanged Alpha158 execution ledger.

    Reads upstream predictions and independent market artifacts. Reuses baseline
    expiry, fees and valuation, writing the standard daily, period, order,
    position and trade artifacts for direct comparison with the policy layer.
    """
