"""Pack complete task groups and build deterministic, bounded transfer archives."""

from __future__ import annotations

import gzip
import os
import tarfile
from collections.abc import Mapping
from pathlib import Path

from ....task.storage.workspace import task_directory
from .models import TAR_PADDING_BYTES, SnapshotChangedError, TaskFile, TaskPlan

SYNC_ARCHIVE_NAME = "axonx-sync.tar.gz"


def build_archive(plans: Mapping[str, TaskPlan], target: Path) -> list[str]:
    included: list[str] = []
    with (
        target.open("wb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=1) as zipped,
        tarfile.open(fileobj=zipped, mode="w") as archive,
    ):
        for task_id, plan in plans.items():
            if not plan.files:
                raise SnapshotChangedError(f"Task snapshot is incomplete: {task_directory(task_id)}")
            for item in plan.files:
                _add_file(archive, task_id, item)
            if any(not item.matches(item.path.stat()) for item in plan.files):
                raise SnapshotChangedError(f"Replica changed while archiving: {task_id}")
            included.append(task_directory(task_id))
    return included


def _add_file(archive: tarfile.TarFile, task_id: str, item: TaskFile) -> None:
    try:
        handle = item.path.open("rb")
    except OSError as exc:
        raise SnapshotChangedError(f"Task file disappeared: {item.path}") from exc
    with handle:
        before = os.fstat(handle.fileno())
        if not item.matches(before):
            raise SnapshotChangedError(f"Task file changed before archiving: {item.path}")
        info = tarfile.TarInfo(f"{task_directory(task_id)}/{item.relative}")
        info.size = item.size
        info.mtime = 0
        info.mode = 0o644
        archive.addfile(info, handle)
        after = os.fstat(handle.fileno())
        if not item.matches(after):
            raise SnapshotChangedError(f"Task file changed while archiving: {item.path}")


def archive_budget(transfer_budget_bytes: int) -> int:
    """Reserve tar padding and worst-case gzip overhead inside the same total budget."""
    return max(0, transfer_budget_bytes - TAR_PADDING_BYTES - max(4096, transfer_budget_bytes // 1024))


def pack_batches(
    groups: Mapping[str, Mapping[str, TaskPlan]], budget: int, max_batches: int
) -> tuple[list[list[str]], list[str], list[str]]:
    """Keep each group atomic and separate groups that share child Tasks."""
    batches: list[list[str]] = []
    rejected: list[str] = []
    current: list[str] = []
    included: set[str] = set()
    used = 0
    for task_id, plans in groups.items():
        if not plans:
            continue
        size = sum(plan.size for plan in plans.values())
        if size > budget:
            rejected.append(task_id)
            continue
        identities = plans.keys()
        if current and (used + size > budget or included & identities):
            batches.append(current)
            current, used = [], 0
            included.clear()
        current.append(task_id)
        included.update(identities)
        used += size
    if current:
        batches.append(current)
    deferred = [task_id for batch in batches[max_batches:] for task_id in batch]
    return batches[:max_batches], rejected, deferred
