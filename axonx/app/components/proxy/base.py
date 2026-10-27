"""Proxy component contract, streaming response ownership, and forwarding errors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterable, AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass

from ....utils.async_work import complete_on_cancel
from ..base import BaseComponent


@dataclass(frozen=True, slots=True)
class ProxyResponse:
    """Streaming response returned by a proxy backend."""

    status_code: int
    content: AsyncIterable[bytes]
    headers: tuple[tuple[str, str], ...] = ()
    close: Callable[[], Awaitable[None]] | None = None

    async def iter_bytes(self) -> AsyncIterator[bytes]:
        """Yield the body and always release its upstream transport."""
        try:
            async for chunk in self.content:
                yield chunk
        finally:
            if self.close is not None:
                await complete_on_cancel(self.close())


class ProxyError(Exception):
    """A forwarding failure with the status the HTTP surface should return."""

    def __init__(self, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


class BaseProxyComponent(BaseComponent, ABC):
    """Define the request-forwarding contract for proxy backends."""

    component_type = "proxy"

    @abstractmethod
    async def forward(
        self,
        method: str,
        path: str,
        *,
        query: Sequence[tuple[str, str]] = (),
        headers: Sequence[tuple[str, str]] = (),
        content: bytes | AsyncIterable[bytes] = b"",
    ) -> ProxyResponse:
        """Forward one streaming request and return a streaming response."""
