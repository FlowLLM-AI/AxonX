"""Shared feature conversion for Alpha158 training and prediction."""

from __future__ import annotations

import numpy as np
import polars as pl


def feature_matrix(frame: pl.DataFrame, features: tuple[str, ...]) -> np.ndarray:
    """Convert finite feature values to NumPy, preserving missing-value behavior."""
    return frame.select(
        *(
            pl.when(pl.col(column).cast(pl.Float64, strict=False).is_finite())
            .then(pl.col(column).cast(pl.Float64, strict=False))
            .otherwise(None)
            .alias(column)
            for column in features
        ),
    ).to_numpy()
