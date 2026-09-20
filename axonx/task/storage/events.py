"""Append and incrementally read the replayable Task event journal."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ...components.job.base import JobEvent
from ...constants import AXONX_DEFAULT_ENCODING

LOG_WINDOW_BYTES = 65_536


@dataclass(frozen=True, slots=True)
class TaskLogChunk:
    content: str = ""
    start_offset: int = 0
    next_offset: int = 0
    file_size: int = 0
    has_more_before: bool = False
    has_more_after: bool = False
    reset: bool = False


def append_event(path: Path, event: JobEvent) -> None:
    """Append one complete JSON event line."""
    with path.open("a", encoding=AXONX_DEFAULT_ENCODING) as handle:
        handle.write(event.model_dump_json() + "\n")


def read_event_lines(path: Path, offset: int) -> tuple[int, list[str]]:
    """Read complete lines after a byte offset, resetting after replacement.

    A trailing partial line belongs to the next read. If the journal was
    truncated or atomically replaced, reading restarts at the beginning.
    """
    try:
        size = path.stat().st_size
        if offset > size:
            offset = 0
        with path.open("rb") as handle:
            handle.seek(offset)
            data = handle.read()
    except FileNotFoundError:
        return offset, []
    complete = data.rfind(b"\n")
    if complete < 0:
        return offset, []
    lines = data[:complete].decode(AXONX_DEFAULT_ENCODING, errors="replace").splitlines()
    return offset + complete + 1, lines
