"""Source identities and verified replica indexes use the same transfer policy."""

import hashlib
import re
from collections.abc import Sequence
from pathlib import Path

from ...constants import TASK_NAME_PATTERN
from ...utils import get_logger
from ...utils.fs import file_sha256
from ..schemas.protocol import fingerprint
from ..storage.workspace import read_entry, scan_entries, task_path
from .errors import SnapshotChangedError
from .planner import plan_task


def validate_task_names(values: Sequence[str] | None) -> frozenset[str]:
    if values is not None and not isinstance(values, (list, tuple, set, frozenset)):
        raise ValueError("task_names must be a list of task names")
    if any(not isinstance(value, str) or not re.fullmatch(TASK_NAME_PATTERN, value) for value in values or ()):
        raise ValueError("task_names must contain valid task names")
    return frozenset(values or ())


def matches_task_name(task_id: str, task_names: frozenset[str]) -> bool:
    return not task_names or task_id.rsplit("#", 1)[-1] in task_names


def policy_digest(budget: int) -> str:
    return fingerprint(
        {
            "format": "display-replica-1",
            "budget": budget,
            "sampling": "latest-whole-days",
        }
    )


def snapshot_digest(root: Path, task_id: str) -> str:
    plan = plan_task(root, task_id)
    digest = hashlib.sha256()
    for item in plan.files:
        digest.update(item.relative.encode("utf-8") + b"\0")
        digest.update(bytes.fromhex(file_sha256(item.path)))
    if plan != plan_task(root, task_id):
        raise SnapshotChangedError(f"Task changed during reconciliation: {task_id}")
    return digest.hexdigest()


def verify_replica(root: Path, task_id: str) -> None:
    metadata = read_entry(root, task_id)
    if (
        metadata is None
        or metadata.replica is None
        or (not metadata.state.is_terminal and metadata.replica.snapshot is None)
    ):
        raise ValueError(f"Task is not a display replica: {task_id}")
    directory = task_path(root, task_id)
    actual = {p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file()}
    if actual != {"metadata.json", *metadata.replica.files}:
        raise ValueError(f"Replica file manifest differs from its directory: {task_id}")
    log = metadata.replica.log
    if log is not None:
        record = metadata.replica.files.get(log.path)
        if record is None or log.end - log.start != record.size:
            raise ValueError(f"Invalid replica log range: {task_id}")
    for name, record in metadata.replica.files.items():
        relative = Path(name)
        path = directory / relative
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or any(p.is_symlink() for p in (path, *path.parents) if p != directory.parent)
        ):
            raise ValueError(f"Invalid replica path: {name}")
        if path.stat().st_size != record.size or file_sha256(path) != record.sha256:
            raise ValueError(f"Replica artifact checksum mismatch: {task_id}/{name}")


def snapshot_index(root: Path, task_names: frozenset[str], roots: frozenset[str] = frozenset()) -> dict:
    """One verified index for all selected display replicas."""
    result = {}
    for identity, metadata in scan_entries(root).items():
        replica = metadata.replica
        if replica is None:
            continue
        selected = metadata.state.is_terminal and matches_task_name(identity, task_names)
        if not selected and not (replica.snapshot and replica.snapshot.root_task_id in roots):
            continue
        try:
            verify_replica(root, identity)
            result[identity] = {
                "source_digest": replica.source_digest,
                "policy_digest": replica.policy_digest,
                "run_id": metadata.run_id,
                "files": {name: item.sha256 for name, item in replica.files.items()},
            }
        except (OSError, ValueError) as exc:
            get_logger("task-sync-index").warning(f"Skipping invalid display replica {identity}: {exc}")
    return result


def validate_live_task_ids(values) -> frozenset[str]:
    from ..core.identity import task_type_from_id

    if values is not None and not isinstance(values, (list, tuple, set, frozenset)):
        raise ValueError("live_task_ids must be a list of Task IDs")
    for value in values or ():
        task_type_from_id(value)
    return frozenset(values or ())
