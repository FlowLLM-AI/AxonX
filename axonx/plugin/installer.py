"""Install inspected plugin wheels and their external dependencies."""

from importlib import invalidate_caches
import subprocess
import sys

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from .models import PluginArtifact


def install_artifact(artifact: PluginArtifact) -> None:
    """Install plugin dependencies without replacing AxonX, then install its wheel."""
    dependencies = [value for value in artifact.requirements if canonicalize_name(Requirement(value).name) != "axonx"]
    commands = []
    if dependencies:
        commands.append([sys.executable, "-m", "pip", "install", *dependencies])
    commands.append(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "--force-reinstall",
            "--no-deps",
            str(artifact.wheel),
        ],
    )
    for command in commands:
        result = subprocess.run(command, check=False, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(
                f"Plugin installation failed: {(result.stderr or result.stdout).strip()}",
            )
    invalidate_caches()
