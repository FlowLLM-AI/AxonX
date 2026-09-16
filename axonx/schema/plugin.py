"""Validated plugin manifest and inspected wheel metadata."""

from pathlib import Path
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


class PluginArtifact(BaseModel):
    """Metadata and contributions read directly from one wheel."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    distribution: str
    version: str
    plugin_names: tuple[str, ...]
    tasks: dict[str, str]
    requirements: tuple[str, ...]
    wheel: Path
    sha256: str
    components: dict[str, dict[str, str]]
    jobs: dict[str, JobConfig]

    def contributions_dict(self) -> dict:
        """Return JSON-compatible manifest contributions."""
        return {
            "tasks": self.tasks,
            "components": self.components,
            "jobs": {name: config.model_dump(mode="json", exclude_unset=True) for name, config in self.jobs.items()},
        }
