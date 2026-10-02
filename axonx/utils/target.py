"""Canonical AxonX service target addresses."""

from ipaddress import ip_address
from urllib.parse import urlsplit

from ..constants import (
    AXONX_DEFAULT_CONNECT_HOST,
    AXONX_DEFAULT_PORT,
    AXONX_DEFAULT_SCHEME,
)


def normalize_target(value: str) -> str:
    """Accept host:port or an HTTP(S) URL and return a canonical service URL."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("target must be a non-empty host:port or HTTP(S) URL")
    raw = value.strip()
    parsed = urlsplit(raw if "://" in raw else f"{AXONX_DEFAULT_SCHEME}://{raw}")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"Invalid target port: {value!r}") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or port is None or not 1 <= port <= 65535:
        raise ValueError(f"Invalid target: {value!r}; expected host:port or HTTP(S) URL")
    if (
        parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(f"Invalid target: {value!r}; expected host:port or HTTP(S) URL")
    host = parsed.hostname
    try:
        host = ip_address(host).compressed
    except ValueError:
        pass
    if ":" in host:
        host = f"[{host}]"
    return f"{parsed.scheme}://{host}:{port}"


def default_target() -> str:
    return normalize_target(f"{AXONX_DEFAULT_CONNECT_HOST}:{AXONX_DEFAULT_PORT}")
