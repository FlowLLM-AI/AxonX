"""Plan complete Task snapshots and bounded archive batches."""

from __future__ import annotations

import os
from pathlib import Path

from ..storage.workspace import task_path
from .models import TaskFile, TaskPlan

ARCHIVE_HEADROOM_BYTES = 4096


def plan_task(root: Path, task_id: str, max_file_bytes: int) -> TaskPlan:
    directory = task_path(root, task_id)
    files: list[TaskFile] = []
    rejected: list[str] = []
    for path in sorted(directory.rglob("*")):
        if os.path.islink(path) or not path.is_file():
            continue
        relative = path.relative_to(directory).as_posix()
        try:
            stat = path.stat()
        except OSError:
            rejected.append(relative)
            continue
        if stat.st_size > max_file_bytes:
            rejected.append(relative)
            continue
        files.append(
            TaskFile(path, relative, stat.st_size, stat.st_mtime_ns, stat.st_ino)
        )
    return TaskPlan(
        tuple(files),
        tuple(sorted(rejected)),
        sum(file.archived_bytes for file in files),
    )


def archive_budget(max_archive_bytes: int) -> int:
    reserve = max(ARCHIVE_HEADROOM_BYTES, max_archive_bytes // 1024)
    return max(max_archive_bytes - reserve, 1)


def pack_batches(
    plans: dict[str, TaskPlan],
    budget: int,
    max_batches: int,
) -> tuple[list[list[str]], list[str], list[str]]:
    batches: list[list[str]] = []
    rejected: list[str] = []
    current: list[str] = []
    used = 0
    for task_id in sorted(plans):
        plan = plans[task_id]
        if plan.empty:
            continue
        if not plan.transferable or plan.size > budget:
            rejected.append(task_id)
            continue
        if current and used + plan.size > budget:
            batches.append(current)
            current, used = [], 0
        current.append(task_id)
        used += plan.size
    if current:
        batches.append(current)
    deferred = [task_id for batch in batches[max_batches:] for task_id in batch]
    return batches[:max_batches], rejected, deferred
