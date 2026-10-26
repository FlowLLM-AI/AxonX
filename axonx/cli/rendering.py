"""Render command results and streamed events for the terminal."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..app.components.job.events import JobEvent


def _json_default(value: object) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def print_json(value: object) -> None:
    """Print one CLI value as readable JSON."""
    print(json.dumps(value, ensure_ascii=False, default=_json_default))


def _event_blocks(event: JobEvent) -> list[tuple[str, object]]:
    """Split one event into labelled blocks without dropping message fields."""
    from ..app.components.agent.events import AgentMessageEvent

    if not isinstance(event, AgentMessageEvent):
        return [(type(event).__name__, event.model_dump(mode="json"))]
    if event.presentation:
        return [
            (f"Agent / {patch.block_type} / {patch.operation}", patch.model_dump(mode="json"))
            for patch in event.presentation
        ]
    return [(f"Agent / {event.type_name}", event.model_dump(mode="json"))]


def print_event_blocks(event: JobEvent) -> None:
    """Print every event block immediately with an explicit type marker."""
    for label, payload in _event_blocks(event):
        print(f"\n===== BLOCK: {label} =====", flush=True)
        print(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            flush=True,
        )
