"""Public plugin artifact and installed-environment models."""

from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from ..config import JobConfig


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
    components: dict[str, dict[str, str]]
    jobs: dict[str, JobConfig]

    def contributions_dict(self) -> dict:
        return {
            "tasks": dict(self.tasks),
            "components": {
                name: dict(backends) for name, backends in self.components.items()
            },
            "jobs": {
                name: config.model_dump(mode="json", exclude_unset=True)
                for name, config in self.jobs.items()
            },
        }


class PluginInfo(BaseModel):
    """One plugin distribution discovered in the active Python environment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    distribution: str
    version: str
    plugins: list[str] = Field(default_factory=list)
    tasks: dict[str, str] = Field(default_factory=dict)
    components: dict[str, dict[str, str]] = Field(default_factory=dict)
    jobs: dict[str, JobConfig] = Field(default_factory=dict)
    requirements: list[str] = Field(default_factory=list)
    content_sha256: str | None = None
    sha256: str | None = None
    error: str | None = None


class PluginInstallResult(PluginInfo):
    """Result returned after installing a plugin wheel."""

    restart_required: bool = False


class PluginUninstallResult(BaseModel):
    """Result returned after uninstalling a plugin distribution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    distribution: str
    restart_required: bool = False
