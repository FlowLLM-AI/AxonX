"""Linear-size frozen history snapshots; portable exports retain the full protocol."""

import json
import re
from pathlib import Path
from typing import Literal

from pydantic import ConfigDict, Field

from ...common.fs.revision import file_revision
from ..task_enums import TaskType
from ..models.artifacts import ArtifactRecord, Protocol
from ..models.reports import OnlineCommit, OnlineHistory

HISTORY_BLOCK_SIZE = 16


class HistoryNode(Protocol):
    """A bounded revision group referencing the preceding completed group."""

    model_config = ConfigDict(extra="forbid")
    task_type: Literal[TaskType.INFERENCE] = TaskType.INFERENCE
    kind: Literal["online_history_node"] = "online_history_node"
    strategy_identity: str = Field(pattern=r"^[0-9a-f]{64}$")
    commits: list[OnlineCommit] = Field(min_length=1, max_length=HISTORY_BLOCK_SIZE)
    previous: ArtifactRecord | None = None


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
    commits = []
    visited: set[str] = set()
    while isinstance(value, dict) and value.get("kind") == "online_history_node":
        node = HistoryNode.model_validate(value)
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
        path = task_dir / reference.path
        if not path.resolve().is_relative_to(task_dir.resolve()) or any(
            parent.is_symlink() for parent in (path, *path.parents) if parent.is_relative_to(task_dir)
        ):
            raise ValueError("Frozen history reference escapes its Task")
        revision = file_revision(path)
        content = path.read_bytes()
        if len(content) != reference.size or revision != reference.revision or file_revision(path) != revision:
            raise ValueError("Frozen history revision mismatch")
        value = json.loads(content)
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
