"""Identity of the AxonX build this process is running."""

from __future__ import annotations

import os
import subprocess
from functools import cache
from importlib import metadata
from pathlib import Path

from .models import BuildInfo

# Distribution this package is published as, and the source tree holding it.
PACKAGE_NAME = "axonx"
PACKAGE_ROOT = Path(__file__).resolve().parents[4]

# A build system may publish the revision it built, for deployments that run
# without the checkout the package came from.
GIT_COMMIT_ENV = "AXONX_GIT_COMMIT"
GIT_BRANCH_ENV = "AXONX_GIT_BRANCH"

# Identity is read once per process, so a slow or blocked repository may only
# hold up the first caller for this long.
GIT_TIMEOUT_SECONDS = 2.0


@cache
def package_version(package: str = PACKAGE_NAME) -> str | None:
    """Return one installed distribution's version, or None when it is not installed."""
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return None


@cache
def get_build_info() -> BuildInfo:
    """Return one consistent build identity snapshot for this process."""
    from ...._version import __version__

    return BuildInfo(
        version=package_version() or __version__,
        git_commit=os.environ.get(GIT_COMMIT_ENV) or _git("rev-parse", "HEAD"),
        git_branch=os.environ.get(GIT_BRANCH_ENV) or _git("branch", "--show-current"),
    )


def _git(*arguments: str) -> str | None:
    """Run one read-only git query in this package's source tree."""
    try:
        result = subprocess.run(
            ["git", "-C", str(PACKAGE_ROOT), *arguments],
            capture_output=True,
            check=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None
