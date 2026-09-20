"""Transport-neutral request metadata and responses for Jobs."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class JobResponse(BaseModel):
    """Canonical result of a Job invocation across every transport."""

    answer: Any = Field(default="", description="response content")
    success: bool = Field(default=True, description="whether succeeded")
    metadata: dict = Field(default_factory=dict, description="metadata")

    def fail(self, error: BaseException) -> JobResponse:
        self.success = False
        self.answer = f"{type(error).__name__}: {error}"
        return self


class JobInfo(BaseModel):
    """Public description of one invocable Job."""

    name: str
    description: str = ""
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]


class JobCatalog(BaseModel):
    """Public catalog of invocable Jobs."""

    items: list[JobInfo] = Field(default_factory=list)
    total: int = 0


__all__ = ["JobCatalog", "JobInfo", "JobResponse"]
