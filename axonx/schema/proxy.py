"""Validated response model shared by proxy backends and consumers."""

from pydantic import BaseModel, ConfigDict, Field


class ProxyResponse(BaseModel):
    """Represent an unwrapped response returned by a proxy component."""

    model_config = ConfigDict(frozen=True)

    status_code: int = Field(ge=100, le=599)
    content: bytes
    headers: dict[str, str] = Field(default_factory=dict)
