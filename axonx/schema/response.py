"""Job response models shared by local and remote transports."""

from typing import Any

from pydantic import BaseModel, Field


class Response(BaseModel):
    """Represent the result of one job invocation."""

    answer: str | Any = Field(default="", description="response content")
    success: bool = Field(default=True, description="whether succeeded")
    metadata: dict = Field(default_factory=dict, description="metadata")
