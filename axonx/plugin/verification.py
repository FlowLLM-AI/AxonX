"""Compare installed plugin wheels before submitting remote Tasks."""

from __future__ import annotations

from importlib import metadata
import json
from typing import Any

from packaging.utils import canonicalize_name

from ..constants import PLUGIN_ENTRY_POINT_GROUP, PLUGIN_MANIFEST
from .manifest import parse_plugin_manifest


def installed_plugin_for_task(task_name: str) -> tuple[str, str | None] | None:
    """Return the installed distribution and original wheel hash for a Task."""
    matches: list[tuple[str, str | None]] = []
    for distribution in metadata.distributions():
        for entry in distribution.entry_points:
            if entry.group != PLUGIN_ENTRY_POINT_GROUP:
                continue
            package = entry.value
            manifest_path = distribution.locate_file(f"{package.replace('.', '/')}/{PLUGIN_MANIFEST}")
            if not manifest_path.is_file():
                raise ValueError(f"Installed plugin {entry.name!r} has no {PLUGIN_MANIFEST}")
            manifest = parse_plugin_manifest(manifest_path.read_text(encoding="utf-8"), entry.name)
            if task_name not in manifest.tasks:
                continue
            name = distribution.metadata["Name"]
            direct_url = distribution.read_text("direct_url.json")
            provenance: dict[str, Any] = json.loads(direct_url) if direct_url else {}
            hashes = provenance.get("archive_info", {}).get("hashes", {})
            digest = hashes.get("sha256")
            if digest is None:
                legacy = provenance.get("archive_info", {}).get("hash", "")
                digest = legacy.removeprefix("sha256=") if legacy.startswith("sha256=") else None
            matches.append((name, digest))
    if len(matches) > 1:
        raise ValueError(f"Task {task_name!r} has multiple locally installed plugin providers")
    return matches[0] if matches else None


def verify_remote_plugin(task_name: str, remote_records: object) -> None:
    """Reject a plugin Task when its installed local and remote wheels differ."""
    if not isinstance(remote_records, list):
        raise ValueError("Remote plugin list has an invalid response")
    matches = [
        record
        for record in remote_records
        if isinstance(record, dict) and task_name in record.get("tasks", {})
    ]
    local = installed_plugin_for_task(task_name)
    if not matches:
        if local is not None:
            raise ValueError(
                f"Task {task_name!r} is provided by locally installed plugin {local[0]!r}, "
                "but the remote service has no managed wheel for it. Deploy the plugin before submitting.",
            )
        return
    if len(matches) != 1:
        raise ValueError(f"Task {task_name!r} has multiple remote plugin providers")
    remote = matches[0]
    if local is None:
        raise ValueError(f"Task {task_name!r} is provided by a remote plugin but is not installed locally")
    local_name, local_hash = local
    remote_name = remote.get("distribution", "")
    if canonicalize_name(local_name) != canonicalize_name(remote_name):
        raise ValueError(
            f"Task {task_name!r} has different plugin providers: local {local_name!r}, remote {remote_name!r}",
        )
    if not local_hash:
        raise ValueError(
            f"Cannot verify locally installed plugin {local_name!r}: its wheel SHA-256 is unavailable. "
            "Install it locally from a wheel before submitting remote Tasks.",
        )
    remote_hash = remote.get("wheel_sha256")
    if local_hash != remote_hash:
        raise ValueError(
            f"Plugin {local_name!r} wheel SHA-256 differs for Task {task_name!r}: "
            f"local {local_hash}, remote {remote_hash or 'missing'}. "
            "Install the plugin locally and deploy the same source to the remote service before submitting.",
        )
