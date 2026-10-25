"""Start independent exec processes from one named crontab file."""

import asyncio
import os
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ..common.locator import locate_file
from ..common.logging import get_logger
from ..common.runtime import AXONX_TASK_LOG_DIR, AXONX_TASK_TIMEZONE, AXONX_TASK_WORKSPACE_DIR
from ..common.workspace import Workspace
from .parser import CronEntry, parse_crontab


class CronScheduler:
    """Own future triggers; running exec processes outlive the scheduler."""

    def __init__(
        self,
        source: str | Path,
        *,
        workspace_dir: str,
        log_dir: str,
        timezone: str,
        environment: dict[str, str],
        launch: Callable[[CronEntry], None],
    ) -> None:
        self.path = locate_file(
            source, directory=Path(__file__).parent, extensions=(".cron",), group="axonx.crons", label="Cron"
        )
        self.entries = parse_crontab(self.path.read_text(encoding="utf-8"))
        self.timezone = ZoneInfo(timezone)
        self.log_dir = str(Path(log_dir).expanduser().resolve())
        self.cwd = Path.cwd().resolve()
        self.environment = {
            **os.environ,
            **environment,
            AXONX_TASK_WORKSPACE_DIR: str(Workspace(workspace_dir).root),
            AXONX_TASK_LOG_DIR: str(Path(log_dir).expanduser().resolve()),
            AXONX_TASK_TIMEZONE: timezone,
        }
        self.logger = get_logger("CronScheduler")
        self._launch = launch
        self._next: dict[int, datetime] = {}
        self._runner: asyncio.Task | None = None
        self._stopping = False

    async def start(self) -> None:
        if self._runner is not None:
            return
        now = datetime.now(self.timezone)
        # Resolve every next occurrence before starting the loop or any child.
        self._next = {entry.line: entry.next_after(now) for entry in self.entries}
        self._stopping = False
        self._runner = asyncio.create_task(self._run(), name="axonx-cron")

    def stop(self) -> None:
        """Stop new launches without signalling any running command."""
        self._stopping = True

    async def close(self) -> None:
        self.stop()
        runner, self._runner = self._runner, None
        if runner is not None:
            runner.cancel()
            with suppress(asyncio.CancelledError):
                await runner
        self._next.clear()

    async def _run(self) -> None:
        while not self._stopping:
            self._tick(datetime.now(self.timezone))
            await asyncio.sleep(0.5)

    def _tick(self, now: datetime) -> None:
        for entry in self.entries:
            if self._stopping or self._next[entry.line].timestamp() > now.timestamp():
                continue
            # Advance before spawning: a failed launch is not retried in the same slot.
            self._next[entry.line] = entry.next_after(now)
            try:
                self._launch(entry)
            except (OSError, RuntimeError):
                self.logger.exception(f"Cron launch failed: {self.path}:{entry.line}")
