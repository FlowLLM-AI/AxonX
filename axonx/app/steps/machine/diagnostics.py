"""Read-only execution environment diagnostics for the selected service."""

import os
import platform
import shutil
import sys
from pathlib import Path

from ....plugin import list_installed_plugins
from .metrics import collect_machine_info

CREDENTIAL_NAMES = ("AXONX_SERVICE_TOKEN", "AXONX_TARGET_TOKEN", "AXONX_TUSHARE_TOKEN")


def collect_diagnostics(workspace: Path, logger) -> dict:
    """Inspect installed state and the workspace filesystem without creating files."""
    workspace = workspace.resolve()
    disk_path = workspace
    while not disk_path.exists() and disk_path != disk_path.parent:
        disk_path = disk_path.parent
    disk = shutil.disk_usage(disk_path)
    plugins = list_installed_plugins()
    return {
        **collect_machine_info(0.1, logger).model_dump(mode="json"),
        "python": {"version": platform.python_version(), "executable": sys.executable},
        "platform": platform.system(),
        "cwd": str(Path.cwd()),
        "workspace": {
            "path": str(workspace),
            "exists": workspace.exists(),
            "disk": {
                "path": str(disk_path),
                "total_bytes": disk.total,
                "used_bytes": disk.used,
                "free_bytes": disk.free,
            },
        },
        "plugins": [
            plugin.model_dump(include={"distribution", "version", "plugins", "content_sha256", "sha256", "error"})
            for plugin in plugins
        ],
        "credentials_configured": {name: bool(os.environ.get(name)) for name in CREDENTIAL_NAMES},
    }
