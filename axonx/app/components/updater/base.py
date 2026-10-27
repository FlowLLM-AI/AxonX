"""Update operations supplied by the application host."""

from typing import Protocol


class UpdateBackend(Protocol):
    """Operations supplied by the process supervisor or an embedding host."""

    def prepare(self, mode: str) -> dict:
        """Prepare an update without stopping the current response."""

    def commit(self, update_id: str) -> None:
        """Commit after the response has been sent."""

    def status(self, update_id: str | None = None) -> dict:
        """Read durable update state."""
