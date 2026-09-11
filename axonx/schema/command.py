"""Validated command produced by the AxonX CLI parser."""

from typing import Any, Annotated

from pydantic import BaseModel, ConfigDict, Field

CommandAction = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")]


class Command(BaseModel):
    """One parsed command, independent of its execution strategy."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    action: CommandAction
    arguments: dict[str, Any] = Field(default_factory=dict)
