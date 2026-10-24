"""Process-level shutdown deadline, independent of asyncio and executor drains."""

import os
import threading

import uvicorn

from .....common.logging import get_logger


class ShutdownServer(uvicorn.Server):
    """Notify the service before Uvicorn starts waiting for ASGI cleanup."""

    def __init__(self, config, on_shutdown):
        super().__init__(config)
        self.on_shutdown = on_shutdown

    def handle_exit(self, sig, frame):
        super().handle_exit(sig, frame)
        self.on_shutdown(force=self.force_exit)


class ShutdownDeadline:
    """A daemon watchdog also covers blocked event loops and executor shutdown."""

    def __init__(self, app, timeout):
        self.app = app
        self.timer = threading.Timer(timeout, self.force_exit)
        self.timer.daemon = True
        self.started = False

    def request(self, *, force=False):
        if force:
            self.force_exit()
            return
        if not self.started:
            self.started = True
            self.timer.start()
            try:
                self.app.request_shutdown()
            except Exception:
                # Keep Uvicorn's shutdown path alive; Application.close retries
                # requests and aggregates errors while the deadline still applies.
                get_logger("HttpService").exception("Failed to request worker shutdown")

    def force_exit(self):
        # Do not await locks, logging handlers or filesystem writes here: they
        # may be the reason graceful shutdown cannot finish. Only owned workers
        # are signalled; workspace records never select processes to kill.
        try:
            self.app.context.service.stop_cli_processes(force=True)
            self.app.request_shutdown()
        finally:
            try:
                blocking = os.get_blocking(2)
                try:
                    os.set_blocking(2, False)
                    os.write(2, b"AxonX: forcing shutdown; application cleanup did not finish.\n")
                finally:
                    os.set_blocking(2, blocking)
            except OSError:
                pass
            os._exit(130)

    def close(self):
        self.timer.cancel()
