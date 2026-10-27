"""HTTP request envelopes for the public Job surface."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class JobInvocation(BaseModel):
    """HTTP-only envelope separating Job arguments from transport targeting."""

    model_config = ConfigDict(extra="forbid")
    arguments: dict[str, Any] = Field(default_factory=dict)
    target: str | None = None
