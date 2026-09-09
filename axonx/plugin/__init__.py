"""Task-only plugin manifests and wheel artifacts."""

from .artifact import (
    PluginArtifact,
    build_wheel,
    inspect_wheel,
    install_artifact,
    source_sha256,
)

__all__ = [
    "PluginArtifact",
    "build_wheel",
    "inspect_wheel",
    "install_artifact",
    "source_sha256",
]
