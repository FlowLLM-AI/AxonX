"""Non-blocking status delivery from a synchronous worker."""

from __future__ import annotations

import socket
from queue import Queue
from threading import Thread

from ..schema import TaskStatus

_STOP = object()


class SocketStatusSink:
    """Write JSON-line status snapshots on a dedicated lightweight thread."""

    def __init__(self, stream: socket.socket, logger) -> None:
        self._stream = stream
        self._logger = logger
        self._queue: Queue[bytes | object] = Queue()
        self._thread: Thread | None = None

    def __enter__(self):
        self._thread = Thread(target=self._write, name="task-status", daemon=True)
        self._thread.start()
        return self

    def publish(self, status: TaskStatus) -> None:
        """Queue a serialized snapshot without blocking the Task step."""
        self._queue.put(status.model_dump_json().encode("utf-8") + b"\n")

    def __exit__(self, *_exc) -> None:
        self._queue.put(_STOP)
        assert self._thread is not None
        self._thread.join()
        self._stream.close()

    def _write(self) -> None:
        while (payload := self._queue.get()) is not _STOP:
            try:
                self._stream.sendall(payload)
            except OSError as exc:
                self._logger.warning(f"Task status update failed: {exc}")
                return
