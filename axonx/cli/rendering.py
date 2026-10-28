"""Render command results and streamed events for the terminal."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from ..client.events import JobEvent


def _json_default(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def print_json(value: object, *, indent: int | None = None, flush: bool = False) -> None:
    """Print one CLI value as readable JSON."""
    print(json.dumps(value, ensure_ascii=False, default=_json_default, indent=indent), flush=flush)


def print_event_blocks(event: JobEvent) -> None:
    """Print every event block immediately without dropping message fields."""
    from ..client.events import AgentMessageEvent

    if isinstance(event, AgentMessageEvent):
        blocks = (
            [(f"Agent / {patch.block_type} / {patch.operation}", patch) for patch in event.presentation]
            if event.presentation
            else [(f"Agent / {event.type_name}", event)]
        )
    else:
        blocks = [(type(event).__name__, event)]
    for label, payload in blocks:
        print(f"\n===== BLOCK: {label} =====", flush=True)
        print_json(payload, indent=2, flush=True)
