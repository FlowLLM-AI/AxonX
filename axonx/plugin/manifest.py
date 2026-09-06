"""Read and parse the declarative plugin contract shared by runtime and CLI."""

from importlib import resources

import yaml
from pydantic import ValidationError

from ..constants import PLUGIN_MANIFEST
from ..schema.plugin import PluginManifest


def parse_plugin_manifest(text: str, *, plugin_name: str) -> PluginManifest:
    """Parse and validate plugin.yaml without importing backend modules."""
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


def load_package_manifest(package: str, *, plugin_name: str) -> PluginManifest:
    """Read plugin.yaml from an importable package."""
    try:
        path = resources.files(package).joinpath(PLUGIN_MANIFEST)
        text = path.read_text(encoding="utf-8")
    except (ModuleNotFoundError, FileNotFoundError, TypeError) as exc:
        raise ValueError(f"Plugin '{plugin_name}' does not provide {package}/{PLUGIN_MANIFEST}") from exc
    return parse_plugin_manifest(text, plugin_name=plugin_name)
