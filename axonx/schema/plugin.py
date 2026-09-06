"""Validated data declared by an AxonX plugin manifest."""

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class PluginManifest(BaseModel):
    """Declarative contributions loaded from a plugin's ``plugin.yaml``."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    backends: dict[NonEmptyString, NonEmptyString] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
