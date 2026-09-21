"""Compare installed plugin contents before submitting remote Tasks."""

from __future__ import annotations

from packaging.utils import canonicalize_name

from ..components.client import BaseClient
from .discovery import installed_plugin_for_task

SUBMIT_JOB = "submit"


def verify_remote_plugin(task_name: str, remote_records: object) -> None:
    """Reject a plugin Task when its local and remote contents differ."""
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
                "but the remote service does not provide it. Deploy the plugin before submitting.",
            )
        return
    if len(matches) != 1:
        raise ValueError(f"Task {task_name!r} has multiple remote plugin providers")
    remote = matches[0]
    if local is None:
        raise ValueError(
            f"Task {task_name!r} is provided by a remote plugin but is not installed locally"
        )
    local_name, local_content_hash, local_wheel_hash = local
    remote_name = remote.get("distribution", "")
    if canonicalize_name(local_name) != canonicalize_name(remote_name):
        raise ValueError(
            f"Task {task_name!r} has different plugin providers: local {local_name!r}, remote {remote_name!r}",
        )
    remote_content_hash = remote.get("content_sha256")
    if local_content_hash and remote_content_hash:
        if local_content_hash == remote_content_hash:
            return
        raise ValueError(
            f"Plugin {local_name!r} content SHA-256 differs for Task {task_name!r}: "
            f"local {local_content_hash}, remote {remote_content_hash}. "
            "Install or deploy the same plugin content before submitting.",
        )
    remote_wheel_hash = remote.get("sha256")
    if local_wheel_hash and remote_wheel_hash:
        if local_wheel_hash == remote_wheel_hash:
            return
        raise ValueError(
            f"Plugin {local_name!r} wheel SHA-256 differs for Task {task_name!r}: "
            f"local {local_wheel_hash}, remote {remote_wheel_hash}. "
            "Install the plugin locally and deploy the same source to the remote service before submitting.",
        )
    raise ValueError(
        f"Cannot verify plugin {local_name!r} for Task {task_name!r}: "
        "a shared content or wheel SHA-256 is unavailable. "
        "Upgrade both AxonX services so plugin content fingerprints are reported.",
    )


async def verify_remote_submission(
    client: BaseClient,
    job_name: str,
    arguments,
) -> None:
    """Verify plugin content identity before sending a Task submission."""
    if job_name != SUBMIT_JOB:
        return
    task_name = arguments.get("task")
    if not isinstance(task_name, str) or not task_name:
        return
    listing = await client.run_job("list_plugins")
    if not listing.success:
        raise ValueError(f"Cannot verify remote plugins: {listing.answer}")
    verify_remote_plugin(task_name, listing.answer)
