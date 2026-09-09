"""Read and parse a Task-only plugin manifest."""

import yaml
from pydantic import ValidationError

from ..schema.plugin import PluginManifest


def parse_plugin_manifest(text: str, *, plugin_name: str) -> PluginManifest:
    """Parse and validate plugin.yaml without importing Task modules."""
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
