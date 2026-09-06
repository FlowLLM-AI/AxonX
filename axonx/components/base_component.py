"""Asynchronous component lifecycle."""

import asyncio

from .component_mixin import ComponentMixin


class BaseComponent(ComponentMixin):
    """Provide idempotent, concurrency-safe asynchronous lifecycle methods."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.is_started = False
        self._lifecycle_lock = asyncio.Lock()

    async def start(self):
        """Start this component once and clean up a partial failed start."""
        async with self._lifecycle_lock:
            if self.is_started:
                return
            try:
                await self._start()
            except BaseException:
                try:
                    await self._close()
                except Exception:
                    self.logger.exception("Startup cleanup failed")
                raise
            self.is_started = True

    async def close(self):
        """Close this component once if it has successfully started."""
        async with self._lifecycle_lock:
            if self.is_started:
                try:
                    await self._close()
                finally:
                    self.is_started = False

    async def _start(self):
        pass

    async def _close(self):
        pass

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *_):
        await self.close()
