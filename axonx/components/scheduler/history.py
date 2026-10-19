"""Bounded, atomic trigger history shared by Job and Task schedules."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from pydantic_core import PydanticSerializationError

from ...enums import TaskState
from ...task.schemas.lifecycle import ScheduleTrigger
from ...utils.fs import atomic_write_json


class ScheduleRun(ScheduleTrigger):
    model_config = ConfigDict(extra="forbid")
    state: TaskState
    error: str = ""
    finished_at: str | None = None
    result: Any = None


class ScheduleHistory(BaseModel):
    runs: list[ScheduleRun] = Field(default_factory=list)


def history_path(workspace: Path, name: str) -> Path:
    return workspace / "schedules" / f"{sha256(name.encode()).hexdigest()}.json"


def load_history(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = ScheduleHistory.model_validate_json(path.read_text()).model_dump(mode="json")["runs"]
    for record in records:
        if record["state"] == "running":
            record.update(
                state="cancelled", error="Service stopped before completion", finished_at=datetime.now(UTC).isoformat()
            )
    return records


def save_history(path: Path, records: list[dict], retention_days: int = 7) -> None:
    """Keep active triggers and outcomes finished within the retention window."""
    if isinstance(retention_days, bool) or not isinstance(retention_days, int) or retention_days < 1:
        raise ValueError("history_retention_days must be a positive integer")
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)

    def keep(record: dict) -> bool:
        if record["state"] == "running":
            return True
        finished = datetime.fromisoformat(record.get("finished_at") or record["triggered_at"])
        # Older records may omit the timezone; interpret them as UTC.
        if finished.tzinfo is None:
            finished = finished.replace(tzinfo=UTC)
        return finished >= cutoff

    records[:] = [record for record in records if keep(record)]
    atomic_write_json(path, {"runs": records})


def trigger_result(answer: Any) -> Any:
    import json

    try:
        encoded = TypeAdapter(Any).dump_json(answer)
    except PydanticSerializationError:
        return {"summary": str(answer)[:16384], "truncated": True}
    return (
        json.loads(encoded)
        if len(encoded) <= 16384
        else {"summary": encoded[:16384].decode("utf-8", "ignore"), "truncated": True}
    )
