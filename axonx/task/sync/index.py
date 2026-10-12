"""Content-based indexes for startup reconciliation, without replica state files."""

import hashlib
import re
import sys
from collections.abc import Sequence
from pathlib import Path

from ...constants import TASK_NAME_PATTERN
from ...utils import get_logger
from ...utils.fs import file_sha256
from ..storage.workspace import read_entry, scan_entries
from .archive import SnapshotChangedError
from .planner import plan_task


def validate_task_names(values: Sequence[str] | None) -> frozenset[str]:
    """Validate the only supported sender filter; an empty list includes all names."""
    if values is not None and not isinstance(values, (list, tuple, set, frozenset)):
        raise ValueError("task_names must be a list of task names")
    if any(not isinstance(value, str) or not re.fullmatch(TASK_NAME_PATTERN, value) for value in values or ()):
        raise ValueError("task_names must contain valid task names")
    return frozenset(values or ())


def matches_task_name(task_id: str, task_names: frozenset[str]) -> bool:
    """Match the final canonical ID segment, independent of type and registration."""
    return not task_names or task_id.rsplit("#", 1)[-1] in task_names


def snapshot_digest(root: Path, task_id: str) -> str:
    """Hash a stable terminal snapshot, including file names and metadata content."""
    plan = plan_task(root, task_id, sys.maxsize)
    if not plan.transferable:
        raise SnapshotChangedError(f"Incomplete Task snapshot: {task_id}")
    digest = hashlib.sha256()
    for item in plan.files:
        digest.update(item.relative.encode("utf-8") + b"\0")
        digest.update(bytes.fromhex(file_sha256(item.path)))
    metadata = read_entry(root, task_id)
    if plan != plan_task(root, task_id, sys.maxsize) or metadata is None or not metadata.state.is_terminal:
        raise SnapshotChangedError(f"Task changed during reconciliation: {task_id}")
    return digest.hexdigest()


def snapshot_index(root: Path, task_names: frozenset[str]) -> dict[str, str]:
    """Index matching terminal snapshots; one changing Task must not abort the whole scan."""
    result = {}
    for task_id, metadata in scan_entries(root).items():
        if metadata.state.is_terminal and matches_task_name(task_id, task_names):
            try:
                result[task_id] = snapshot_digest(root, task_id)
            except OSError as exc:
                get_logger("task-sync-index").warning(f"Skipping Task snapshot {task_id}: {exc}")
    return result
