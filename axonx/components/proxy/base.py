"""Base contract shared by proxy component backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence

from ...enums import ComponentEnum
from ...schema import ProxyResponse
from ..base import BaseComponent


class BaseProxyComponent(BaseComponent, ABC):
    """Define the request-forwarding contract for proxy backends."""

    component_type = ComponentEnum.PROXY

    @abstractmethod
    async def forward(
        self,
        method: str,
        path: str,
        *,
        query: Sequence[tuple[str, str]] = (),
        headers: Mapping[str, str] | None = None,
        content: bytes = b"",
    ) -> ProxyResponse:
        """Forward one request and return its unwrapped response."""
