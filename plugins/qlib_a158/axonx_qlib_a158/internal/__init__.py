"""Alpha158 domain calculations and reference definitions.

etl_pipeline: Market-data preparation, calendars, price limits and index weights.
features: Price/rolling expressions and dataset statistics.
analysis: Polars-based factor diagnostics.
modeling: Shared NumPy feature conversion for training and prediction.
protocol: Plugin-owned feature contracts and semantic fingerprints.
reference: Qlib provenance, parameter presets and workflow deviations.
"""

from . import analysis, etl_pipeline, features, modeling, protocol, reference

__all__ = [
    "analysis",
    "etl_pipeline",
    "features",
    "modeling",
    "protocol",
    "reference",
]
