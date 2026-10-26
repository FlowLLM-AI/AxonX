"""One atomic manifest publishes immutable online artifacts and revision history."""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from ..models.artifacts import PROTOCOL_VERSION
from ..models.reports import HISTORY_BLOCK_SIZE, HistoryNode, OnlineCommit, OnlineHistory
from .artifacts import artifact_record, verify_artifact
from .files import atomic_write, atomic_write_json, file_lock, file_revision, snapshot_file
from .workspace import resolve_relative_path

if TYPE_CHECKING:
    from ..core.clock import DeadlineBudget


def read_online_history(path: Path) -> OnlineHistory:
    """Read full v1 histories or verified frozen chains, without recursive traversal."""
    path = Path(path).absolute()
    content = path.read_bytes()
    value = json.loads(content)
    if not isinstance(value, dict) or value.get("kind") != "online_history_node":
        return OnlineHistory.model_validate(value)
    # Node references are Task-relative, matching artifact manifests and sync.
    # A node may only live in its reserved commit directory.
    if path.name != "history.json" or path.parent.parent.name != "commits":
        raise ValueError("Frozen history node must belong to an online commit directory")
    task_dir = path.parents[4]
    if path.parent.parent.parent != task_dir / "persistent" / "online":
        raise ValueError("Invalid frozen history directory")
    header = HistoryNode.model_validate(value)
    node = header
    commits = []
    visited: set[str] = set()
    while True:
        if node.strategy_identity != header.strategy_identity:
            raise ValueError("Frozen history strategy changed")
        if node.commits[-1].commit_id != path.parent.name or node.commits[-1].commit_id in visited:
            raise ValueError("Invalid or cyclic frozen history")
        visited.add(node.commits[-1].commit_id)
        commits.append(node.commits)
        if node.previous is None:
            value = {
                "version": node.version,
                "strategy_identity": node.strategy_identity,
                "commits": [],
            }
            break
        reference = node.previous
        if re.fullmatch(r"persistent/online/commits/[0-9a-f]{32}/history\.json", reference.path) is None:
            raise ValueError("Invalid frozen history reference")
        path = verify_artifact(task_dir, reference)
        content = path.read_bytes()
        if len(content) != reference.size or file_revision(path) != reference.revision:
            raise ValueError("Frozen history revision mismatch")
        value = json.loads(content)
        if not isinstance(value, dict) or value.get("kind") != "online_history_node":
            break
        node = HistoryNode.model_validate(value)
    base = OnlineHistory.model_validate(value)
    if base.strategy_identity != header.strategy_identity:
        raise ValueError("Frozen history strategy changed")
    return OnlineHistory(
        version=header.version,
        strategy_identity=header.strategy_identity,
        commits=[
            *base.commits,
            *(commit for block in reversed(commits) for commit in block),
        ],
    )


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
        """Prepare outside the lease; only the final history check and swap exclude other writers."""
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
                snapshot_file(source, target, isolated=True, expected_revision=revision)
                records[role] = artifact_record(target, self.task.task_dir)
            budget.check()
            commit = OnlineCommit(
                commit_id=commit_id,
                task_id=self.task.task_id,
                started_at=self.task.metadata.started_at,
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

            with file_lock(self.root / "publication.lock"):
                if history != self.history(history.strategy_identity):
                    raise ValueError("Online history changed before publication; retry with current history")
                atomic_write(self.manifest, publish)
            published = True
            return commit, snapshot
        finally:
            if not published:
                shutil.rmtree(folder, ignore_errors=True)


def pin_online_history(task, upstream_task_id: str, *, as_of: str | None = None) -> tuple[OnlineHistory, Path]:
    """Snapshot the manifest and every referenced artifact, preserving verified provenance."""
    upstream = task.upstream_task_dir(upstream_task_id)
    source = resolve_relative_path(upstream, "persistent/online/manifest.json")
    history = read_online_history(source)
    if any(commit.task_id != upstream_task_id for commit in history.commits):
        raise ValueError("Online history belongs to another Task")
    root = task.task_dir / "inputs" / "online"
    commits = []
    pinned_files: dict[str, Path] = {}
    for commit in history.commits:
        if as_of is not None and commit.trade_date > as_of:
            continue
        records = {}
        for role, record in commit.artifacts.items():
            path = verify_artifact(upstream, record)
            target = root / commit.commit_id / Path(record.path).name
            if record.path in pinned_files:
                snapshot_file(pinned_files[record.path], target, expected_revision=record.revision)
            else:
                # Keep the first copy isolated from in-place upstream writes. Only
                # consumer-owned immutable copies may share storage with one another.
                snapshot_file(path, target, isolated=True, expected_revision=record.revision)
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
