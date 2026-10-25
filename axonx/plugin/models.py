"""Research Task plugin manifests and installation models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


@dataclass(frozen=True, slots=True)
class PluginArtifact:
    """A validated plugin wheel before it is installed."""

    distribution: str
    version: str
    plugin_names: tuple[str, ...]
    tasks: dict[str, str]
    requirements: tuple[str, ...]
    wheel: Path
    content_sha256: str
    sha256: str

    def contributions_dict(self) -> dict:
        return {
            "tasks": dict(self.tasks),
        }


class PluginInfo(BaseModel):
    """One plugin distribution discovered in the active Python environment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    distribution: str
    version: str
    plugins: list[str] = Field(default_factory=list)
    tasks: dict[str, str] = Field(default_factory=dict)
    requirements: list[str] = Field(default_factory=list)
    content_sha256: str | None = None
    sha256: str | None = None
    error: str | None = None


class PluginUninstallResult(BaseModel):
    """Result returned after uninstalling a plugin distribution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    distribution: str


NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class PluginManifest(BaseModel):
    """Contributions declared by one plugin package."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    tasks: dict[NonEmptyString, NonEmptyString] = Field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PluginContributions:
    tasks: dict[str, str]
    task_owners: dict[str, str]
