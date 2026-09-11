"""Private entry point for one isolated Task worker process."""

from __future__ import annotations

import importlib
import json
import os
import socket
import sys
import traceback

from ..components.component_registry import R
from ..constants import AXONX_TASK_STATUS_FD
from .base_task import BaseTask
from .status_sink import SocketStatusSink


def _load_task(target: str) -> type[BaseTask]:
    module_name, qualname = target.split(":", 1)
    with R.preserve(allow_mutation=True):
        task_class = importlib.import_module(module_name)
        for part in qualname.split("."):
            task_class = getattr(task_class, part)
    if not isinstance(task_class, type) or not issubclass(task_class, BaseTask):
        raise TypeError("Task target must subclass BaseTask")
    return task_class


def main() -> int:
    """Read one request from stdin and execute it on the process main thread."""
    try:
        descriptor = int(os.environ[AXONX_TASK_STATUS_FD])
        payload = json.load(sys.stdin)
        task = _load_task(payload["target"])(payload["config"])
        stream = socket.socket(fileno=descriptor)
        with SocketStatusSink(stream, task.logger) as sink:
            task.execute(emit=sink.publish)
        assert task.status.exit_code is not None
        return task.status.exit_code
    except BaseException:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
