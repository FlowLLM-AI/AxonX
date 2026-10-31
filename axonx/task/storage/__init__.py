"""Task persistence, grouped by the resources each module owns.

files: Atomic writes, filesystem revisions, output copies and publication leases.
workspace: Task directory layout, lifecycle records and incremental metadata scans.
artifacts: Published file references and payload size/revision verification.
inputs: Successful upstream records, direct artifact access and source revision checks.
logs: Progress and execution journals, with byte-offset text-log readers.
online: Online result publication in ordinary Task output directories.
"""

from . import artifacts, files, inputs, logs, online, workspace
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
    "reset_task_directory",
    "scan_entries",
    "scan_metadata",
    "task_directory",
    "task_id_from_path",
    "task_path",
    "workspace",
    "write_task_metadata",
]
