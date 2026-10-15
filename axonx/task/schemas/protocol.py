"""Versioned protocol headers and deterministic semantic fingerprints."""

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator

from ...enums import TaskType

PROTOCOL_VERSION = 1
STOCK_SIGNALS_FORMAT = "stock-signals-v1"


class Protocol(BaseModel):
    """Plugins extend the payload; the framework owns version and producer type."""

    model_config = ConfigDict(extra="allow")
    version: Literal[1]
    task_type: TaskType

    @field_validator("version", mode="before")
    @classmethod
    def validate_version(cls, value):
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("Protocol version must be an integer")
        return value


def task_protocol(task_type: TaskType, **payload: Any) -> dict:
    return Protocol(version=PROTOCOL_VERSION, task_type=task_type, **payload).model_dump(mode="json")


def validate_protocol(value: dict, *task_types: TaskType) -> dict:
    header = Protocol.model_validate(value)
    if task_types and header.task_type not in task_types:
        raise ValueError(f"Expected protocol for {task_types}, got {header.task_type}")
    return value


def fingerprint(value: Mapping) -> str:
    """Hash semantic content deterministically, independent of mapping order."""
    content = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(content.encode()).hexdigest()
