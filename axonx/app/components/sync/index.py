"""Source identities and verified replica indexes use the same transfer policy."""

from pathlib import Path

from ....task.models.artifacts import fingerprint
from ....task.models.identity import matches_task_name
from ....task.storage.workspace import read_entry, scan_entries, task_path
from ....utils.logging import get_logger
from .errors import SnapshotChangedError
from .planner import plan_task


def policy_revision(budget: int) -> str:
    return f"display-replica-3:{budget}:latest-whole-days"


def source_revision(root: Path, task_id: str, *, snapshot=None, logs=None) -> str:
    """Identify publications from Task start time and file metadata without reading payloads."""
    plan = plan_task(root, task_id, snapshot=snapshot)
    metadata = snapshot or read_entry(root, task_id)
    if metadata is None:
        raise SnapshotChangedError(f"Task disappeared during reconciliation: {task_id}")
    files = [(item.relative, item.size, item.modified_ns) for item in plan.files]
    log = logs.path(metadata) if logs is not None else None
    if log is not None and logs.is_task_log(log) and log.is_file():
        stat = log.stat()
        files.append(("display/log.log", stat.st_size, stat.st_mtime_ns))
    return fingerprint([metadata.started_at.isoformat(), files])


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
        if path.stat().st_size != record.size:
            raise ValueError(f"Replica artifact size mismatch: {task_id}/{name}")


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
                "started_at": metadata.started_at.isoformat(),
                **replica.model_dump(mode="json"),
            }
        except (OSError, ValueError) as exc:
            get_logger("task-sync-index").warning(f"Skipping invalid display replica {identity}: {exc}")
    return result
