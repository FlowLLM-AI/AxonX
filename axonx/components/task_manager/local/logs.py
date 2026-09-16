"""Locate and validate Task worker log files."""

from pathlib import Path

from ....schema import TaskStatus


class TaskLogLocator:
    """Resolve persisted and legacy worker log paths inside one log directory."""

    def __init__(self, log_dir: Path) -> None:
        self.log_dir = log_dir.expanduser().resolve()

    def sanitize_loaded(self, status: TaskStatus) -> None:
        """Remove a persisted log path that cannot belong to this runtime."""
        if not status.log_path:
            return
        path = Path(status.log_path).expanduser().resolve()
        status.log_path = str(path) if path.suffix == ".log" and path.is_relative_to(self.log_dir) else ""

    def attach(self, status: TaskStatus) -> None:
        """Backfill a missing legacy log path using the worker PID."""
        if status.log_path or status.pid is None or not self.log_dir.is_dir():
            return
        matches = tuple(self.log_dir.glob(f"*_{status.pid}.log"))
        if matches:
            status.log_path = str(max(matches, key=lambda path: path.stat().st_mtime))

    def prepare_loaded(self, statuses: dict[str, TaskStatus]) -> None:
        """Sanitize and backfill every status loaded from disk."""
        for status in statuses.values():
            self.sanitize_loaded(status)
            self.attach(status)

    def attach_all(self, statuses: dict[str, TaskStatus]) -> None:
        """Backfill missing log paths without altering reported paths."""
        for status in statuses.values():
            self.attach(status)
