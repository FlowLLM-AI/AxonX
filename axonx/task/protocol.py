"""Compatibility exports for Task and research artifact protocols."""

from .schemas.protocol import (
    PROTOCOL_VERSION,
    STOCK_SIGNALS_FORMAT,
    Protocol,
    fingerprint,
    task_protocol,
    validate_protocol,
)
from .schemas.model import ModelCollection, ModelMember
from .schemas.prediction import PredictionProtocol
from .schemas.artifact import ArtifactRecord
from .storage.artifacts import prediction_protocol

__all__ = [
    "PROTOCOL_VERSION",
    "STOCK_SIGNALS_FORMAT",
    "Protocol",
    "fingerprint",
    "task_protocol",
    "validate_protocol",
    "ModelCollection",
    "ModelMember",
    "PredictionProtocol",
    "prediction_protocol",
    "ArtifactRecord",
]
