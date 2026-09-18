"""Asynchronous workspace file operations."""

from abc import ABC, abstractmethod
from typing import Any

from ...enums import ComponentEnum
from ..base import BaseComponent


class BaseWorkspaceComponent(BaseComponent, ABC):
    """Backend-independent interface for browsing workspace artifacts."""

    component_type = ComponentEnum.WORKSPACE

    @abstractmethod
    async def list_entries(self, path: str = "", require_metadata: bool = False) -> dict[str, Any]:
        """List one directory within the workspace."""

    @abstractmethod
    async def preview_file(self, path: str, offset: int = 0, limit: int = 200, full: bool = False) -> dict[str, Any]:
        """Preview one supported file."""

    @abstractmethod
    async def delete_entries(self, paths: list[str]) -> list[dict[str, str]]:
        """Validate and delete multiple workspace entries."""
