"""Feature contracts, semantic fingerprints and model input conversion."""

from __future__ import annotations

import numpy as np
import polars as pl

from axonx.task.models.artifacts import fingerprint, task_protocol, validate_protocol
from axonx.task.models.identity import TaskType

FEATURE_FIELDS = (
    "feature_family",
    "trade_time",
    "feature_columns",
    "return_unit",
    "feature_rules",
)


def feature_contract(metadata: dict) -> dict:
    """Validate and retain model semantics without dates, paths or quality counters."""
    validate_protocol(metadata, TaskType.ETL)
    if missing := set(FEATURE_FIELDS) - metadata.keys():
        raise ValueError(f"Incomplete feature protocol: {sorted(missing)}")
    if not isinstance(metadata["feature_family"], str) or not metadata["feature_family"]:
        raise ValueError("Feature protocol requires a family")
    columns = metadata["feature_columns"]
    if (
        not isinstance(columns, list)
        or not columns
        or any(not isinstance(column, str) or not column for column in columns)
        or len(columns) != len(set(columns))
    ):
        raise ValueError("Feature columns must be nonempty, unique names in model order")
    if not isinstance(metadata["feature_rules"], dict):
        raise ValueError("Feature rules must be a mapping")
    return {**task_protocol(TaskType.ETL), **{key: metadata[key] for key in FEATURE_FIELDS}}


def feature_identity(metadata: dict) -> str:
    """Fingerprint the same validated contract stored with the trained model."""
    return fingerprint(feature_contract(metadata))


def feature_matrix(frame: pl.DataFrame, features: tuple[str, ...]) -> np.ndarray:
    """Convert finite feature values to NumPy, preserving missing-value behavior."""
    values = frame.select(pl.col(features).cast(pl.Float64, strict=False))
    return values.select(pl.when(pl.all().is_finite()).then(pl.all())).to_numpy()


def load_lightgbm():
    """Load the modeling runtime when training or scoring."""
    try:
        import lightgbm
    except ImportError as exc:
        raise RuntimeError("Modeling requires lightgbm; install the Alpha158 plugin dependencies") from exc
    return lightgbm
