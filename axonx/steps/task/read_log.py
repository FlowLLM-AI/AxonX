"""Bounded Task-log reader."""

from __future__ import annotations

from pathlib import Path

from ...components.registry import R
from ..base import BaseStep


@R.register("read_task_log")
class ReadTaskLogStep(BaseStep):
    """Read one bounded byte range from the log attached to a Task status."""

    async def execute(self):
        status = await self.task_manager.get_status(self.context["task_id"])
        requested_offset = self.context.get("offset", -1)
        limit = self.context.get("limit", 65_536)
        if not status.log_path:
            self.response.answer = {
                "content": "",
                "start_offset": 0,
                "next_offset": 0,
                "file_size": 0,
                "has_more_before": False,
                "has_more_after": False,
                "reset": False,
            }
            return

        log_root = Path(self.app_config.log_dir).expanduser().resolve()
        path = Path(status.log_path).expanduser().resolve()
        if not path.is_relative_to(log_root) or path.suffix != ".log":
            raise ValueError("Task log path is outside the configured log directory")
        if not path.is_file():
            raise FileNotFoundError(f"Task log does not exist: {path.name}")

        file_size = path.stat().st_size
        reset = requested_offset > file_size
        start_offset = max(0, file_size - limit) if requested_offset < 0 or reset else requested_offset
        with path.open("rb") as file:
            file.seek(start_offset)
            data = file.read(limit)
        next_offset = start_offset + len(data)
        self.response.answer = {
            "content": data.decode("utf-8", errors="replace"),
            "start_offset": start_offset,
            "next_offset": next_offset,
            "file_size": file_size,
            "has_more_before": start_offset > 0,
            "has_more_after": next_offset < file_size,
            "reset": reset,
        }
