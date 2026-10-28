"""Explicit Task worker settings and execution environment."""

from ipaddress import ip_address
from typing import Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator


def normalize_execution_target(value: str | None) -> str | None:
    """Validate an explicitly advertised service address without probing the network."""
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("execution_target must be a non-empty host:port or HTTP(S) URL")
    raw = value.strip()
    try:
        parsed = urlsplit(raw if "://" in raw else f"http://{raw}")
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Invalid execution_target; an explicit service port is required") from exc
    invalid = (
        "Invalid execution_target; expected host:port or an HTTP(S) URL without credentials, paths or query strings"
    )
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or port is None or not 1 <= port <= 65535:
        raise ValueError(invalid)
    if any(
        (
            parsed.username is not None,
            parsed.password is not None,
            parsed.path not in {"", "/"},
            parsed.query,
            parsed.fragment,
            any(character.isspace() for character in parsed.hostname),
        )
    ):
        raise ValueError(invalid)
    host = parsed.hostname
    try:
        address = ip_address(host)
    except ValueError:
        address = None
    local_address = getattr(address, "ipv4_mapped", None) or address
    local_name = host.rstrip(".").lower()
    if (
        local_name == "localhost"
        or local_name.endswith(".localhost")
        or (local_address is not None and (local_address.is_loopback or local_address.is_unspecified))
    ):
        raise ValueError(
            "execution_target must be reachable from other machines; loopback and wildcard hosts are invalid"
        )
    if address is not None:
        host = address.compressed
    if ":" in host:
        host = f"[{host}]"
    return f"{parsed.scheme}://{host}:{port}"


class ExecutionSettings(BaseModel):
    """Settings shared by process workspaces and execution environments."""

    model_config = ConfigDict(extra="ignore", hide_input_in_errors=True)
    workspace_dir: str = ".axonx"
    log_dir: str = "logs"
    log_to_console: bool = True
    log_to_file: bool = True
    timezone: str = "Asia/Shanghai"
    execution_target: str | None = None
    environment: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def resolve_execution_target(self) -> Self:
        self.execution_target = normalize_execution_target(self.execution_target)
        return self
