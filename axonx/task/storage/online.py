"""One atomic manifest publishes immutable online artifacts and revision history."""

import fcntl
import json
import shutil
import re
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from ..schemas.online import OnlineCommit, OnlineHistory
from ..core.clock import DeadlineBudget
from ..schemas.protocol import PROTOCOL_VERSION
from .artifacts import artifact_path, artifact_record
from .history import HISTORY_BLOCK_SIZE, HistoryNode, read_online_history
from ...utils.fs import atomic_write, atomic_write_json, file_revision, snapshot_file


@contextmanager
def publication_lock(path: Path, budget: DeadlineBudget):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as lock:
        while True:
            budget.check()
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                budget.sleep(0.1)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def online_artifact(root: Path, commit: OnlineCommit, role: str) -> Path:
    record = commit.artifacts[role].model_dump()
    path = artifact_path(root, {"output_params": {"artifacts": {role: record}}}, role)
    if path.stat().st_size != record["size"] or file_revision(path) != record["revision"]:
        raise ValueError(f"Online artifact revision mismatch: {role}")
    return path


class OnlineStore:
    """Task-owned history survives reruns. Unreferenced files are never committed."""

    def __init__(self, task):
        self.task = task
        self.root = task.persistent_dir / "online"
        self.manifest = self.root / "manifest.json"

    def history(self, strategy_identity: str) -> OnlineHistory:
        if not self.manifest.exists():
            return OnlineHistory(version=PROTOCOL_VERSION, strategy_identity=strategy_identity)
        history = read_online_history(self.manifest)
        if history.strategy_identity != strategy_identity:
            raise ValueError("Online strategy changed; use a new task_name for a new strategy")
        return history

    def commit(
        self,
        *,
        history: OnlineHistory,
        trade_date: str,
        trade_time: str,
        model_identity: dict[str, str],
        protocol: dict,
        files: dict[str, Path],
        budget: DeadlineBudget,
        prepare: Callable[[OnlineCommit, Path], object] | None = None,
    ) -> tuple[OnlineCommit, Path]:
        """All fallible work precedes the manifest swap; never undo a committed result."""
        with publication_lock(self.root / "publication.lock", budget):
            if history != self.history(history.strategy_identity):
                raise ValueError("Online history changed before publication; retry with current history")
            if any(c.task_id != self.task.task_id for c in history.commits):
                raise ValueError("Online history belongs to another Task")
            previous = None
            boundary = len(history.commits) // HISTORY_BLOCK_SIZE * HISTORY_BLOCK_SIZE
            if boundary:
                previous_path = self.root / "commits" / history.commits[boundary - 1].commit_id / "history.json"
                if not previous_path.is_file():
                    # Portable legacy histories may retain only their latest full snapshot.
                    boundary = len(history.commits)
                    previous_path = self.root / "commits" / history.commits[-1].commit_id / "history.json"
                if previous_path.is_symlink():
                    raise ValueError("Frozen history snapshot cannot be a symlink")
                expected = history.model_copy(update={"commits": history.commits[:boundary]})
                if read_online_history(previous_path) != expected:
                    raise ValueError("Frozen history differs from the current manifest")
                previous = artifact_record(previous_path, self.task.task_dir)
            commit_id = uuid4().hex
            folder = self.root / "commits" / commit_id
            folder.mkdir(parents=True)
            published = False
            try:
                records = {}
                for role, source in files.items():
                    if re.fullmatch(r"[A-Za-z0-9_-]+", role) is None:
                        raise ValueError("Invalid online artifact role")
                    budget.check()
                    # Roles are logical names; source basenames cannot collide across roles.
                    target = folder / f"{role}{source.suffix}"
                    revision = file_revision(source)
                    snapshot_file(source, target, isolated=True)
                    records[role] = artifact_record(target, self.task.task_dir)
                    if records[role]["revision"] != revision:
                        raise ValueError("Online input changed during publication")
                budget.check()
                commit = OnlineCommit(
                    commit_id=commit_id,
                    task_id=self.task.task_id,
                    run_id=self.task.context.run_id,
                    trade_date=trade_date,
                    trade_time=trade_time,
                    revision=1 + sum((c.trade_date, c.trade_time) == (trade_date, trade_time) for c in history.commits),
                    committed_at=budget.clock.now(),
                    model_identity=model_identity,
                    protocol=protocol,
                    artifacts=records,
                )
                updated = OnlineHistory(
                    version=PROTOCOL_VERSION,
                    strategy_identity=history.strategy_identity,
                    commits=[*history.commits, commit],
                )
                snapshot = folder / "history.json"
                node = HistoryNode(
                    version=PROTOCOL_VERSION,
                    strategy_identity=history.strategy_identity,
                    commits=updated.commits[boundary:],
                    previous=previous,
                )
                atomic_write_json(snapshot, node.model_dump(mode="json"))
                if prepare is not None:
                    prepare(commit, snapshot)
                # Serialize once, keeping the public manifest self-contained.
                content = json.dumps(
                    updated.model_dump(mode="json"),
                    ensure_ascii=False,
                    indent=2,
                    allow_nan=False,
                )

                # Check after serialization and immediately before the single publication point.
                def publish(temporary):
                    temporary.write_text(content, encoding="utf-8")
                    budget.check()

                atomic_write(self.manifest, publish)
                published = True
                return commit, snapshot
            finally:
                if not published:
                    shutil.rmtree(folder, ignore_errors=True)


def pin_online_history(task, source_id: str, *, as_of: str | None = None) -> tuple[OnlineHistory, Path]:
    """Snapshot the manifest and every referenced artifact, preserving verified provenance."""
    upstream = task.source_task_dir(source_id)
    source = artifact_path(
        upstream,
        {"output_params": {"artifacts": {"signal_history": {"path": "persistent/online/manifest.json"}}}},
        "signal_history",
    )
    history = read_online_history(source)
    if any(commit.task_id != source_id for commit in history.commits):
        raise ValueError("Online history belongs to another Task")
    root = task.task_dir / "inputs" / "online"
    commits = []
    pinned_files: dict[str, Path] = {}
    for commit in history.commits:
        if as_of is not None and commit.trade_date > as_of:
            continue
        records = {}
        for role, record in commit.artifacts.items():
            path = online_artifact(upstream, commit, role)
            target = root / commit.commit_id / Path(record.path).name
            if record.path in pinned_files:
                snapshot_file(pinned_files[record.path], target)
            else:
                # Keep the first copy isolated from in-place upstream writes. Only
                # consumer-owned immutable copies may share storage with one another.
                snapshot_file(path, target, isolated=True)
            if file_revision(target) != record.revision:
                raise ValueError("Online source changed during snapshot")
            pinned_files[record.path] = target
            records[role] = artifact_record(target, task.task_dir)
        commits.append(OnlineCommit.model_validate({**commit.model_dump(), "artifacts": records}))
    pinned = OnlineHistory(
        version=PROTOCOL_VERSION,
        strategy_identity=history.strategy_identity,
        commits=commits,
    )
    manifest = root / "history.json"
    atomic_write_json(manifest, pinned.model_dump(mode="json"))
    return pinned, manifest
