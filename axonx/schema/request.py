"""Extensible request metadata model retained for compatibility."""

from pydantic import BaseModel, ConfigDict, Field


class Request(BaseModel):
    """Accept metadata plus transport-specific extension fields."""

    model_config = ConfigDict(extra="allow")
    metadata: dict | None = Field(default=None, description="Request metadata")
