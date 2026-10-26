"""The Task-only plugin manifest contract, shared by wheels and installations."""

from collections.abc import Callable, Mapping
from typing import Annotated

import yaml
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

PLUGIN_ENTRY_POINT_GROUP = "axonx.plugins"
PLUGIN_MANIFEST = "plugin.yaml"

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class PluginManifest(BaseModel):
    """Parse package manifests and reject duplicate Task registrations."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    tasks: dict[NonEmptyString, NonEmptyString] = Field(default_factory=dict)

    @classmethod
    def parse(cls, text: str, plugin_name: str) -> "PluginManifest":
        """Validate YAML without importing plugin code."""
        try:
            value = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ValueError(f"Plugin {plugin_name!r} manifest is invalid YAML") from exc
        if not isinstance(value, dict):
            raise ValueError(f"Plugin {plugin_name!r} manifest root must be a mapping")
        try:
            return cls.model_validate(value)
        except ValidationError as exc:
            raise ValueError(f"Plugin {plugin_name!r} manifest is invalid: {exc}") from exc

    @classmethod
    def from_packages(cls, packages: Mapping[str, str], read_manifest: Callable[[str], str]) -> "PluginManifest":
        """Read and merge entry-point packages from a filesystem or archive."""
        tasks: dict[str, str] = {}
        for name, package in packages.items():
            if not all(part.isidentifier() for part in package.split(".")):
                raise ValueError(f"Plugin entry point {name!r} must target a package: {package!r}")
            manifest = cls.parse(read_manifest(package), name)
            duplicates = tasks.keys() & manifest.tasks.keys()
            if duplicates:
                raise ValueError(f"Duplicate Task names in distribution: {', '.join(sorted(duplicates))}")
            tasks.update(manifest.tasks)
        return cls(tasks=tasks)
