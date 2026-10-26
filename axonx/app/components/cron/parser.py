"""Parse five-field schedules and argument vectors without a shell."""

import re
import shlex
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from croniter import croniter

from ...config.locator import locate_file

_FIELD = re.compile(r"^[0-9*,/\-]+$")


@dataclass(frozen=True)
class CronEntry:
    line: int
    cron: str
    command: tuple[str, ...]

    def next_after(self, now: datetime) -> datetime:
        return croniter(self.cron, now).get_next(datetime)


def parse_crontab(text: str) -> tuple[CronEntry, ...]:
    """Validate the complete file before returning any executable entries."""
    entries = []
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            fields = line.split(maxsplit=5)
            if len(fields) != 6 or not all(_FIELD.fullmatch(field) for field in fields[:5]):
                raise ValueError("Expected five numeric cron fields followed by a command")
            expression = " ".join(fields[:5])
            if not croniter.is_valid(expression):
                raise ValueError(f"Invalid cron expression: {expression}")
            argv = shlex.split(fields[5], comments=False)
            if not argv or not argv[0]:
                raise ValueError("A cron entry requires a command")
            entries.append(CronEntry(number, expression, tuple(argv)))
        except ValueError as exc:
            raise ValueError(f"Cron line {number}: {exc}") from exc
    return tuple(entries)


def load_crontab(source: str, validate_command: Callable[[Sequence[str]], None]) -> tuple[Path, tuple[CronEntry, ...]]:
    """Resolve a crontab and validate every command before enabling scheduling."""
    path = locate_file(
        source,
        directory=Path(__file__).resolve().parents[2] / "crontabs",
        extensions=(".cron",),
        group="axonx.crons",
        label="Crontab",
    ).resolve()
    entries = parse_crontab(path.read_text(encoding="utf-8"))
    for entry in entries:
        try:
            validate_command(entry.command)
        except ValueError as exc:
            raise ValueError(f"{path}:{entry.line}: {exc}") from exc
    return path, entries
