"""Application update admission and response-completion handoff."""

from functools import partial
from typing import Protocol

from ...async_work import run_blocking
from ...core.response import RESPONSE_CALLBACKS
from ...registry import provider
from ..base import BaseComponent
from ..component_type import ComponentType


class UpdateBackend(Protocol):
    """Operations supplied by the process supervisor or an embedding host."""

    def prepare(self, mode: str) -> dict:
        """Prepare an update without stopping the current response."""

    def commit(self, update_id: str) -> None:
        """Commit after the response has been sent."""

    def status(self, update_id: str | None = None) -> dict:
        """Read durable update state."""


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
