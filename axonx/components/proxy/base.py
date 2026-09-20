"""Base contract shared by proxy component backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterable, AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import ClassVar

from ...enums import ComponentEnum
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
                await self.close()


class ProxyError(Exception):
    """A refusal a proxy backend reports to its caller as a status code.

    The backend knows *what* went wrong and the HTTP surface that mounted it
    knows how to say so, so the status travels with the error instead of being
    re-derived from the exception type at every route.
    """

    status_code: ClassVar[int] = 502


class ProxyRequestError(ProxyError):
    """The request cannot be forwarded as it was sent."""

    status_code = 422


class ProxyUpstreamError(ProxyError):
    """The upstream could not be reached, or failed while answering."""

    status_code = 502


class ProxyUpstreamTimeoutError(ProxyUpstreamError):
    """The upstream did not answer within the configured timeout."""

    status_code = 504


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
        headers: Sequence[tuple[str, str]] = (),
        content: bytes | AsyncIterable[bytes] = b"",
    ) -> ProxyResponse:
        """Forward one streaming request and return a streaming response."""
