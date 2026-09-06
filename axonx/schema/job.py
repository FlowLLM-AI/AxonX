"""Protocol-neutral description of a remotely callable job."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class JobInfo(BaseModel):
    """Describe a public job and its transport-neutral schemas."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(alias="inputSchema")
    output_schema: dict[str, Any] = Field(alias="outputSchema")
