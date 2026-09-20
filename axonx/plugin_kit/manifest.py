"""Read and parse an AxonX plugin manifest."""

import yaml
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError
from typing import Annotated

from ..config import JobConfig

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class PluginManifest(BaseModel):
    """Contributions declared by one plugin package."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    tasks: dict[NonEmptyString, NonEmptyString] = Field(default_factory=dict)
    components: dict[NonEmptyString, dict[NonEmptyString, NonEmptyString]] = Field(
        default_factory=dict,
    )
    jobs: dict[NonEmptyString, JobConfig] = Field(default_factory=dict)


def parse_plugin_manifest(text: str, plugin_name: str) -> PluginManifest:
    """Parse and validate plugin.yaml without importing plugin modules."""
    try:
        value = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"Plugin '{plugin_name}' manifest is invalid YAML") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Plugin '{plugin_name}' manifest root must be a mapping")

    try:
        return PluginManifest.model_validate(value)
    except ValidationError as exc:
        raise ValueError(f"Plugin '{plugin_name}' manifest is invalid: {exc}") from exc
