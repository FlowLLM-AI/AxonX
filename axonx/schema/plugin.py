"""Validated contributions in an AxonX plugin manifest."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from .application_config import JobConfig

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class PluginManifest(BaseModel):
    """Tasks, component backends, and jobs exported by a plugin package."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    tasks: dict[NonEmptyString, NonEmptyString] = Field(default_factory=dict)
    components: dict[
        NonEmptyString,
        dict[NonEmptyString, NonEmptyString],
    ] = Field(default_factory=dict)
    jobs: dict[NonEmptyString, JobConfig] = Field(default_factory=dict)
