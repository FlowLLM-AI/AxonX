"""Plugin wheel metadata shared by build, inspection, and installation."""

from dataclasses import dataclass
from pathlib import Path

from ..schema import JobConfig


@dataclass(frozen=True)
class PluginArtifact:
    """Metadata and contributions read directly from one wheel."""

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
