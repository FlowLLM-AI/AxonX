"""Build deterministic archives from complete Task snapshot plans."""

from __future__ import annotations

import gzip
import os
import tarfile
from collections.abc import Sequence
from pathlib import Path

from ..storage.workspace import task_directory
from .models import TaskFile, TaskPlan

SYNC_ARCHIVE_NAME = "axonx-sync.tar.gz"


class SnapshotChangedError(OSError):
    """A planned Task changed before its snapshot finished building."""


def build_archive(
    plans: dict[str, TaskPlan], task_ids: Sequence[str], target: Path
) -> list[str]:
    included: list[str] = []
    with (
        target.open("wb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped,
        tarfile.open(fileobj=zipped, mode="w") as archive,
    ):
        for task_id in task_ids:
            plan = plans[task_id]
            if not plan.transferable:
                raise SnapshotChangedError(
                    f"Task snapshot is incomplete: {task_directory(task_id)}"
                )
            for item in plan.files:
                _add_file(archive, task_id, item)
            included.append(task_directory(task_id))
    return included


def _add_file(archive: tarfile.TarFile, task_id: str, item: TaskFile) -> None:
    try:
        handle = item.path.open("rb")
    except OSError as exc:
        raise SnapshotChangedError(f"Task file disappeared: {item.path}") from exc
    with handle:
        before = os.fstat(handle.fileno())
        if (before.st_size, before.st_mtime_ns, before.st_ino) != (
            item.size,
            item.modified_ns,
            item.inode,
        ):
            raise SnapshotChangedError(
                f"Task file changed before archiving: {item.path}"
            )
        info = tarfile.TarInfo(f"{task_directory(task_id)}/{item.relative}")
        info.size = item.size
        info.mtime = 0
        info.mode = 0o644
        archive.addfile(info, handle)
        after = os.fstat(handle.fileno())
        if (after.st_size, after.st_mtime_ns, after.st_ino) != (
            item.size,
            item.modified_ns,
            item.inode,
        ):
            raise SnapshotChangedError(
                f"Task file changed while archiving: {item.path}"
            )
