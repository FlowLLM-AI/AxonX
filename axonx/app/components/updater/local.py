"""Local update admission and response-completion handoff to the host."""

from functools import partial

from ....utils.async_work import run_blocking
from ..job.base import RESPONSE_CALLBACKS
from ..registry import provider
from .base import BaseUpdaterComponent, UpdateBackend


@provider("local")
class LocalUpdaterComponent(BaseUpdaterComponent):
    """Reserve application admission until the host replaces the service.

    The response boundary owns the commit callback. Preparation failures and
    cancellation release admission; accepted updates keep maintenance active.
    """

    async def request(self, mode: str) -> dict:
        callbacks = RESPONSE_CALLBACKS.get()
        if callbacks is None:
            raise RuntimeError("Updates require a response completion boundary")
        context = self._require_context()
        if context.metadata.get("maintenance"):
            raise RuntimeError("An update is already pending")
        backend = self._require_backend()
        # Reserve before yielding so all updater instances share one admission gate.
        context.metadata["maintenance"] = True
        try:
            record = await run_blocking(backend.prepare, mode)
            callbacks.append(partial(backend.commit, record["update_id"]))
            return record
        except BaseException:
            context.metadata.pop("maintenance", None)
            raise

    def status(self, update_id: str | None = None) -> dict:
        return self._require_backend().status(update_id)

    def _require_backend(self) -> UpdateBackend:
        backend = self._require_context().updates
        if backend is None:
            raise RuntimeError("No update backend is configured")
        return backend
