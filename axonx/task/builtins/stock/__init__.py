"""Reusable stock research and portfolio evaluation capabilities.

data: Tabular artifact schemas, key validation, labels and market-state normalization.
protocol: Feature identity, producer/consumer contracts and stock signal formats.
models: Portfolio configuration, Task inputs/outputs and stock report contracts.
ledger: Cash, positions, orders, trades and policy-driven execution accounting.
reporting: Daily diagnostics, benchmarks, portfolio metrics and period summaries.
engine: Backtest input validation, candidate preparation and result assembly.
backtest: Task-level input resolution, universe orchestration and artifact publication.
"""

from . import backtest, data, engine, ledger, models, protocol, reporting

__all__ = [
    "backtest",
    "data",
    "engine",
    "ledger",
    "models",
    "protocol",
    "reporting",
]
