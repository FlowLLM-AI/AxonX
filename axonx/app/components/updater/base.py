"""Component-facing update contract and synchronous host backend protocol."""

from abc import ABC, abstractmethod
from typing import Protocol

from ..base import BaseComponent


class BaseUpdaterComponent(BaseComponent, ABC):
    """Application-facing update admission and status, independent of the host."""

    component_type = "updater"

    @abstractmethod
    async def request(self, mode: str) -> dict:
        """Prepare an update and defer its commit to the response boundary."""

    @abstractmethod
    def status(self, update_id: str | None = None) -> dict:
        """Read the latest or selected update state."""


class UpdateBackend(Protocol):
    """Host-owned validation, process changes and durable records.

    The host defines supported modes and record fields; the component only
    requires prepare() to return an update_id for the deferred commit.
    """

    def prepare(self, mode: str) -> dict:
        """Prepare an update without stopping the current response."""

    def commit(self, update_id: str) -> None:
        """Commit after the response has been sent."""

    def status(self, update_id: str | None = None) -> dict:
        """Read durable update state."""
