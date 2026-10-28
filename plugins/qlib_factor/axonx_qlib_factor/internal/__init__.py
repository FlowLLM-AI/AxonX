"""Causal market and stock context calculations.

cross_section: Global market moments, feature groups and context protocols.
stock_context: Market-neutral momentum and return risk from prior market beta.
"""

from . import cross_section, stock_context

__all__ = [
    "cross_section",
    "stock_context",
]
