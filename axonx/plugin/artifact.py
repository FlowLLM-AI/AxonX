"""Compatibility imports for plugin artifact operations."""

import subprocess  # Kept for callers patching artifact.subprocess.run.

from .builder import build_wheel, source_sha256
from .inspector import inspect_wheel
from .installer import install_artifact
from .models import PluginArtifact

__all__ = ["PluginArtifact", "build_wheel", "inspect_wheel", "install_artifact", "source_sha256", "subprocess"]
