"""Validated Task declarations in an AxonX plugin manifest."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class PluginManifest(BaseModel):
    """Tasks exported by a plugin package."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    tasks: dict[NonEmptyString, NonEmptyString] = Field(default_factory=dict)
