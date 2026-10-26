"""Shared model policy and scalar validation for Task contracts."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict


class TaskModel(BaseModel):
    """Reject undeclared fields at Task data boundaries."""

    model_config = ConfigDict(extra="forbid")


def normalize_yyyymmdd(value: object, *, optional: bool = False) -> str | None:
    """Validate a calendar date and return its canonical YYYYMMDD representation."""
    if optional and (value is None or isinstance(value, str) and value.lower() in {"", "none"}):
        return None
    normalized = str(value)
    try:
        parsed = datetime.strptime(normalized, "%Y%m%d")
    except ValueError as exc:
        raise ValueError(f"必须是有效 YYYYMMDD: {normalized}") from exc
    if parsed.strftime("%Y%m%d") != normalized:
        raise ValueError(f"必须是有效 YYYYMMDD: {normalized}")
    return normalized


DateString = Annotated[str, BeforeValidator(normalize_yyyymmdd)]
