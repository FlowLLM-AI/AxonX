"""Parse five-field crontab entries containing local AxonX exec commands."""

import re
import shlex
from dataclasses import dataclass
from datetime import datetime

from croniter import croniter

from ..constants import CLI_CLIENT_OPTIONS

_FIELD = re.compile(r"^[0-9*,/\-]+$")
_OPTION = re.compile(r"^--[A-Za-z][A-Za-z0-9_-]*(?:\.[A-Za-z][A-Za-z0-9_-]*)*$")


@dataclass(frozen=True)
class CronEntry:
    line: int
    cron: str
    arguments: tuple[str, ...]

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
                raise ValueError("Expected five numeric cron fields followed by axonx exec --task NAME")
            expression = " ".join(fields[:5])
            if not croniter.is_valid(expression):
                raise ValueError(f"Invalid cron expression: {expression}")
            argv = shlex.split(fields[5], comments=False)
            if argv[:2] != ["axonx", "exec"]:
                raise ValueError("Only axonx exec --task NAME is supported")
            arguments = argv[2:]
            if len(arguments) % 2:
                raise ValueError("Task options must be pairs like --field value")
            options = set()
            for option, value in zip(arguments[::2], arguments[1::2], strict=True):
                if not _OPTION.fullmatch(option) or value.startswith("--"):
                    raise ValueError(f"Invalid Task option: {option}")
                name = option[2:].replace("-", "_")
                if name in CLI_CLIENT_OPTIONS:
                    raise ValueError(f"Client option is not supported in cron: {option}")
                if name in options:
                    raise ValueError(f"Duplicate Task option: {option}")
                options.add(name)
            if "task" not in options or not arguments[arguments.index("--task") + 1]:
                raise ValueError("A cron command requires --task NAME")
            entries.append(CronEntry(number, expression, tuple(arguments)))
        except ValueError as exc:
            raise ValueError(f"Cron line {number}: {exc}") from exc
    return tuple(entries)
