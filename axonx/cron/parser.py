"""Parse five-field crontab entries containing local AxonX exec commands."""

import re
import shlex
from dataclasses import dataclass
from datetime import datetime

from croniter import croniter

from ..config.target import CLIENT_OPTION_NAMES
from ..common.arguments import parse_arguments

_FIELD = re.compile(r"^[0-9*,/\-]+$")


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
            options = parse_arguments(arguments)
            for option in arguments[::2]:
                name = option[2:].replace("-", "_")
                if name in CLIENT_OPTION_NAMES:
                    raise ValueError(f"Client option is not supported in cron: {option}")
            if not isinstance(options.get("task"), str) or not options["task"]:
                raise ValueError("A cron command requires --task NAME")
            entries.append(CronEntry(number, expression, tuple(arguments)))
        except ValueError as exc:
            raise ValueError(f"Cron line {number}: {exc}") from exc
    return tuple(entries)
