"""Synchronous Task authoring, grouped by responsibility.

base: BaseTask, child Task calls, typed output publication and step contracts.
clock: Real business time and monotonic deadline budgets.
research: ETL, analysis, training, prediction, backtest and comparison bases.
windows: Window scheduling, realtime collection and fixed-model inference bases.
"""

from . import base, clock, research, windows

__all__ = [
    "base",
    "clock",
    "research",
    "windows",
]
