"""Application update admission and response-completion handoff."""

from functools import partial

from ....utils.async_work import run_blocking
from ..base import BaseComponent
from ..job.response import RESPONSE_CALLBACKS
from ..models import ComponentType
from ..registry import provider
from .base import UpdateBackend


@provider("local")
class UpdateManager(BaseComponent):
    """Own admission while the injected backend owns process changes."""

    component_type = ComponentType.UPDATER

    @property
    def operations(self) -> UpdateBackend:
        backend = self.app_context.updates
        if backend is None:
            raise RuntimeError("No update backend is configured")
        return backend

    async def request(self, mode: str) -> dict:
        callbacks = RESPONSE_CALLBACKS.get()
        if callbacks is None:
            raise RuntimeError("Updates require a response completion boundary")
        if self.app_context.metadata.get("maintenance"):
            raise RuntimeError("An update is already pending")
        self.app_context.metadata["maintenance"] = True
        try:
            operations = self.operations
            record = await run_blocking(operations.prepare, mode)
            callbacks.append(partial(operations.commit, record["update_id"]))
            return record
        except BaseException:
            self.app_context.metadata.pop("maintenance", None)
            raise

    def status(self, update_id: str | None = None) -> dict:
        return self.operations.status(update_id)
