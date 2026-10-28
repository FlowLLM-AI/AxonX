"""Shared connection options, service addresses and wire conventions."""

from ipaddress import ip_address
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, PositiveFloat, field_validator

AXONX_DEFAULT_CONNECT_HOST = "127.0.0.1"
AXONX_DEFAULT_PORT = 1024
AXONX_DEFAULT_SCHEME = "http"
AXONX_DEFAULT_REQUEST_TIMEOUT = 60.0
AXONX_DEFAULT_TARGET = f"{AXONX_DEFAULT_SCHEME}://{AXONX_DEFAULT_CONNECT_HOST}:{AXONX_DEFAULT_PORT}"

AXONX_SERVICE_TARGET = "AXONX_SERVICE_TARGET"
AXONX_CLI_REQUEST_ID = "AXONX_CLI_REQUEST_ID"
TARGET_ARGUMENT = "target"

PROTOCOL_ROUTE_HEALTH = "/health"
PROTOCOL_ROUTE_JOBS = "/jobs"
PROTOCOL_ROUTE_JOB = "/jobs/{name}"
PROTOCOL_ROUTE_JOB_EVENTS = "/jobs/{name}/events"
PROTOCOL_ROUTE_UPLOAD = "/upload"
PROTOCOL_ROUTE_MCP = "/mcp"

PROTOCOL_AUTH_HEADER = "authorization"
PROTOCOL_AUTH_SCHEME = "Bearer"
PROTOCOL_CLI_REQUEST_HEADER = "X-AxonX-Cli-Request"
PROTOCOL_FILE_NAME_HEADER = "x-file-name"
PROTOCOL_FILE_DIRECTORY_HEADER = "x-file-directory"
PROTOCOL_SSE_MEDIA_TYPE = "text/event-stream"
PROTOCOL_SSE_EVENT_PREFIX = "event: "
PROTOCOL_SSE_DATA_PREFIX = "data: "


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


class ConnectionOptions(BaseModel):
    """Validated connection options; an omitted target permits service discovery."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    target: str | None = None
    timeout: PositiveFloat = AXONX_DEFAULT_REQUEST_TIMEOUT
    token: str | None = Field(default=None, min_length=1, repr=False)

    @field_validator("target")
    @classmethod
    def validate_target(cls, value: str | None) -> str | None:
        return normalize_target(value) if value is not None else None
