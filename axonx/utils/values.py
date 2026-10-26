"""Scalar conversion shared by CLI arguments and environment expansion."""

import json
import re
from typing import Any

_LEADING_ZERO_RE = re.compile(r"^-?0\d")


def convert_value(value: str) -> Any:
    """Convert text to a Python scalar or JSON value, preserving leading zeros."""
    value = value.strip()
    lower = value.lower()
    if lower in {"none", "null"}:
        return None
    if lower in {"true", "false"}:
        return lower == "true"

    if not _LEADING_ZERO_RE.match(value):
        for converter in (int, float):
            try:
                return converter(value)
            except ValueError:
                pass

    try:
        return json.loads(value)
    except ValueError:
        return value
