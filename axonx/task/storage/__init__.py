"""Task persistence, grouped by the resources each module owns.

files: Atomic writes, filesystem revisions, snapshots and publication leases.
workspace: Task directory layout, lifecycle records and incremental metadata scans.
artifacts: Published file references and payload size/revision verification.
inputs: Successful upstream records, artifact bundles and model-collection snapshots.
logs: Append-only progress journals and byte-offset text-log readers.
online: Atomic online commits, frozen history chains and pinned histories.
replay: Portable replay manifests and isolated payload snapshots.
"""

from . import artifacts, files, inputs, logs, online, replay, workspace
from .workspace import (
    EVENTS_FILE,
    KINDS,
    LOG_FILE,
    METADATA_FILE,
    PERSISTENT_DIR,
    FileVersion,
    is_task_directory,
    parse_task_directory,
    read_entry,
    read_task_metadata,
    reset_task_directory,
    scan_entries,
    scan_metadata,
    task_directory,
    task_id_from_path,
    task_path,
    write_task_metadata,
)

__all__ = [
    "EVENTS_FILE",
    "FileVersion",
    "KINDS",
    "LOG_FILE",
    "METADATA_FILE",
    "PERSISTENT_DIR",
    "artifacts",
    "files",
    "inputs",
    "is_task_directory",
    "logs",
    "online",
    "parse_task_directory",
    "read_entry",
    "read_task_metadata",
    "replay",
    "reset_task_directory",
    "scan_entries",
    "scan_metadata",
    "task_directory",
    "task_id_from_path",
    "task_path",
    "workspace",
    "write_task_metadata",
]
