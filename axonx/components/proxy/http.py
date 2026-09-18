"""Configurable asynchronous HTTP reverse proxy."""

from __future__ import annotations

import hmac
import json
from collections.abc import Mapping, Sequence
from typing import Any

import httpx

from ...schema import ProxyResponse
from ..registry import R
from .base import BaseProxyComponent

_REQUEST_HEADER_ALLOWLIST = frozenset({"accept", "content-type", "user-agent"})
_RESPONSE_HEADER_ALLOWLIST = frozenset(
    {
        "cache-control",
        "content-language",
        "content-type",
        "etag",
        "expires",
        "last-modified",
        "retry-after",
    },
)


def _parse_path(path: str) -> tuple[str, ...]:
    """Validate and split a dotted JSON field path."""
    parts = tuple(path.split("."))
    if any(not part for part in parts):
        raise ValueError(f"Invalid JSON field path: {path!r}")
    return parts


def _read_path(value: Mapping[str, Any], path: Sequence[str]) -> Any:
    """Return a nested field, or None when it is absent."""
    current: Any = value
    for part in path:
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def _write_path(value: dict[str, Any], path: Sequence[str], replacement: Any) -> None:
    """Replace a nested field, creating missing parent objects."""
    current = value
    for part in path[:-1]:
        child = current.get(part)
        if child is None:
            child = {}
            current[part] = child
        if not isinstance(child, dict):
            raise ValueError(f"Cannot replace nested JSON field: {'.'.join(path)}")
        current = child
    current[path[-1]] = replacement


def _load_object(content: bytes) -> dict[str, Any]:
    """Decode a proxy request body as a JSON object."""
    try:
        payload = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Proxy request body must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("Proxy request body must be a JSON object")
    return payload


def _dump_object(payload: dict[str, Any]) -> bytes:
    """Encode a transformed JSON object for forwarding."""
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()


@R.register("http")
class HttpProxyComponent(BaseProxyComponent):
    """Own an HTTP client and apply configured request transformations."""

    def __init__(
        self,
        upstream_base_url: str,
        timeout: float = 600,
        request_secret: str | None = None,
        request_secret_header: str | None = None,
        request_secret_json_path: str | None = None,
        json_overrides: Mapping[str, Any] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.upstream_base_url = upstream_base_url.rstrip("/")
        if not self.upstream_base_url:
            raise ValueError("Proxy upstream_base_url must not be empty")
        if timeout <= 0:
            raise ValueError("Proxy timeout must be greater than 0")
        if request_secret is not None and not isinstance(request_secret, str):
            raise TypeError("Proxy request_secret must be a string")
        secret_sources = tuple(
            source for source in (request_secret_header, request_secret_json_path) if source is not None
        )
        if request_secret is not None and len(secret_sources) != 1:
            raise ValueError("Configure exactly one proxy request-secret source")
        if request_secret is None and secret_sources:
            raise ValueError("Proxy request-secret source requires request_secret")
        if request_secret_header is not None and not request_secret_header.strip():
            raise ValueError("Proxy request_secret_header must not be empty")

        self.timeout = timeout
        self.request_secret = request_secret
        self.request_secret_header = request_secret_header.lower() if request_secret_header is not None else None
        self.request_secret_json_path = (
            _parse_path(request_secret_json_path) if request_secret_json_path is not None else None
        )
        self.json_overrides = tuple(
            (_parse_path(path), replacement) for path, replacement in (json_overrides or {}).items()
        )
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    async def _start(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=f"{self.upstream_base_url}/",
            timeout=self.timeout,
            transport=self._transport,
        )

    async def _close(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            await client.aclose()

    def _require_secret(self, supplied: Any) -> None:
        if not isinstance(supplied, str) or not hmac.compare_digest(supplied, self.request_secret or ""):
            raise PermissionError("Invalid proxy request secret")

    def _prepare_content(self, content: bytes) -> bytes:
        needs_json = self.request_secret_json_path is not None or bool(self.json_overrides)
        if not needs_json:
            return content
        payload = _load_object(content)

        if self.request_secret_json_path is not None:
            self._require_secret(_read_path(payload, self.request_secret_json_path))
        for path, replacement in self.json_overrides:
            _write_path(payload, path, replacement)
        return _dump_object(payload)

    async def forward(
        self,
        method: str,
        path: str,
        *,
        query: Sequence[tuple[str, str]] = (),
        headers: Mapping[str, str] | None = None,
        content: bytes = b"",
    ) -> ProxyResponse:
        """Forward one request and return the unwrapped upstream response."""
        if self._client is None:
            raise RuntimeError("Proxy component is not running")
        if not path or any(part in {"", ".", ".."} for part in path.split("/")):
            raise ValueError("Invalid proxy request path")

        incoming_headers = {key.lower(): value for key, value in (headers or {}).items()}
        if self.request_secret_header is not None:
            self._require_secret(incoming_headers.get(self.request_secret_header))
        prepared = self._prepare_content(content)
        forwarded_headers = {key: value for key, value in incoming_headers.items() if key in _REQUEST_HEADER_ALLOWLIST}
        if self.request_secret_json_path is not None or self.json_overrides:
            forwarded_headers["content-type"] = "application/json"

        response = await self._client.request(
            method,
            path,
            params=query,
            headers=forwarded_headers,
            content=prepared,
        )
        return ProxyResponse(
            status_code=response.status_code,
            content=response.content,
            headers={
                key: value for key, value in response.headers.items() if key.lower() in _RESPONSE_HEADER_ALLOWLIST
            },
        )
