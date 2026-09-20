"""Durable acknowledgement state for one remote Task replica."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ...constants import AXONX_DEFAULT_ENCODING
from ...task.core.identity import task_type_from_id
from ...utils.fs import atomic_write_json


class SyncStateStore:
    """Persist which Task IDs a remote node has acknowledged."""

    def __init__(self, workspace: Path, remote: str) -> None:
        key = hashlib.sha256(remote.encode()).hexdigest()[:16]
        self.path = workspace / "sync" / f"{key}.json"

    def load(self) -> set[str]:
        try:
            value = json.loads(self.path.read_text(encoding=AXONX_DEFAULT_ENCODING))
        except FileNotFoundError:
            return set()
        except (OSError, UnicodeError, ValueError) as exc:
            raise ValueError(f"Cannot read sync state: {self.path}") from exc
        task_ids = value.get("acknowledged") if isinstance(value, dict) else None
        if not isinstance(task_ids, list) or not all(
            isinstance(task_id, str) for task_id in task_ids
        ):
            raise ValueError(f"Invalid sync state: {self.path}")
        for task_id in task_ids:
            task_type_from_id(task_id)
        return set(task_ids)

    def save(self, task_ids: set[str]) -> None:
        atomic_write_json(self.path, {"acknowledged": sorted(task_ids)})
