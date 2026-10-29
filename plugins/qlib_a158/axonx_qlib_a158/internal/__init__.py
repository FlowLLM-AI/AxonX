"""Alpha158 domain calculations and reference definitions.

market: Market-data preparation, calendars, price limits and index weights.
features: Alpha158 definitions, price/rolling expressions and dataset statistics.
analysis: Polars-based factor diagnostics.
modeling: Feature contracts, semantic fingerprints and NumPy model inputs.
reference: Qlib provenance, parameter presets and workflow deviations.
"""

from . import analysis, features, market, modeling, reference

__all__ = [
    "analysis",
    "features",
    "market",
    "modeling",
    "reference",
]
