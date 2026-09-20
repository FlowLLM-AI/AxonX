"""Compare installed plugin wheels before submitting remote Tasks."""

from __future__ import annotations

from packaging.utils import canonicalize_name

from ..components.client import BaseClient
from .discovery import installed_plugin_for_task

SUBMIT_JOB = "submit"


def verify_remote_plugin(task_name: str, remote_records: object) -> None:
    """Reject a plugin Task when its installed local and remote wheels differ."""
    if not isinstance(remote_records, list):
        raise TypeError("Remote plugin list has an invalid response")
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
        raise ValueError(
            f"Task {task_name!r} is provided by a remote plugin but is not installed locally"
        )
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
    remote_hash = remote.get("sha256")
    if local_hash != remote_hash:
        raise ValueError(
            f"Plugin {local_name!r} wheel SHA-256 differs for Task {task_name!r}: "
            f"local {local_hash}, remote {remote_hash or 'missing'}. "
            "Install the plugin locally and deploy the same source to the remote service before submitting.",
        )


async def verify_remote_submission(
    client: BaseClient,
    job_name: str,
    arguments,
) -> None:
    """Verify plugin wheel identity before sending a Task submission."""
    if job_name != SUBMIT_JOB:
        return
    task_name = arguments.get("task")
    if not isinstance(task_name, str) or not task_name:
        return
    listing = await client.run_job("list_plugins")
    if not listing.success:
        raise ValueError(f"Cannot verify remote plugins: {listing.answer}")
    verify_remote_plugin(task_name, listing.answer)
