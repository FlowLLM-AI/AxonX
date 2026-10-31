"""Publish one online result in its Task's ordinary output directory."""

import re
from pathlib import Path
from uuid import uuid4

from ..models.reports import OnlineCommit
from .artifacts import artifact_record
from .files import copy_file, file_revision


def publish_online(task, *, trade_date, trade_time, model_identity, protocol, files, budget) -> OnlineCommit:
    """Only returned artifact records are published; the executor owns the Task lock."""
    folder = task.task_dir / "outputs" / trade_time
    records = {}
    for role, source in files.items():
        if re.fullmatch(r"[A-Za-z0-9_-]+", role) is None:
            raise ValueError("Invalid online artifact role")
        budget.check()
        source = Path(source)
        target = folder / f"{role}{source.suffix}"
        copy_file(source, target, expected_revision=file_revision(source))
        records[role] = artifact_record(target, task.task_dir)
    budget.check()
    return OnlineCommit(
        commit_id=uuid4().hex,
        task_id=task.task_id,
        started_at=task.metadata.started_at,
        trade_date=trade_date,
        trade_time=trade_time,
        revision=1,
        committed_at=budget.clock.now(),
        model_identity=model_identity,
        protocol=protocol,
        artifacts=records,
    )
