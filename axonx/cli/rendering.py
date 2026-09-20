"""Startup banner with AxonX runtime metadata."""

import colorsys
import json
import random
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..components.job.events import BackendEvent, JobEvent
from ..constants import (
    AXONX_DEFAULT_BIND_HOST,
    AXONX_DEFAULT_CONNECT_HOST,
    AXONX_DEFAULT_PORT,
    AXONX_DEFAULT_SCHEME,
    PROTOCOL_ROUTE_MCP,
)
from ..utils.build_info import get_build_info, package_version

if TYPE_CHECKING:
    from ..components.service import BaseService
    from ..config import ApplicationConfig


def _version(package_name: str) -> str:
    """Return one dependency's version for the banner, blank when it is absent."""
    return package_version(package_name) or ""


def _rgb(hue: float) -> tuple[int, int, int]:
    red, green, blue = colorsys.hsv_to_rgb(hue % 1.0, 0.85, 0.98)
    return int(red * 255), int(green * 255), int(blue * 255)


def print_logo(app_config: "ApplicationConfig", service: "BaseService") -> None:
    """Print the AxonX logo and effective service endpoints."""
    ascii_art = (
        r" █████╗ ██╗  ██╗ ██████╗ ███╗   ██╗██╗  ██╗",
        r"██╔══██╗╚██╗██╔╝██╔═══██╗████╗  ██║╚██╗██╔╝",
        r"███████║ ╚███╔╝ ██║   ██║██╔██╗ ██║ ╚███╔╝ ",
        r"██╔══██║ ██╔██╗ ██║   ██║██║╚██╗██║ ██╔██╗ ",
        r"██║  ██║██╔╝ ██╗╚██████╔╝██║ ╚████║██╔╝ ██╗",
        r"╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝╚═╝  ╚═╝",
    )

    hue_base = random.random()
    logo = Text()
    for line_number, line in enumerate(ascii_art):
        for position, character in enumerate(line):
            red, green, blue = _rgb(
                hue_base + line_number * 0.08 + position / max(1, len(line) - 1) * 0.5
            )
            logo.append(character, style=f"bold rgb({red},{green},{blue})")
        logo.append("\n")

    host = getattr(service, "host", AXONX_DEFAULT_BIND_HOST)
    port = getattr(service, "port", AXONX_DEFAULT_PORT)
    display_host = (
        AXONX_DEFAULT_CONNECT_HOST if host == AXONX_DEFAULT_BIND_HOST else host
    )
    url = f"{AXONX_DEFAULT_SCHEME}://{display_host}:{port}"
    info = Table.grid(padding=(0, 1))
    info.add_column(style="bold", justify="center")
    info.add_column(style="bold cyan")
    info.add_column(style="white")
    info.add_row("📦", "Backend:", "http")
    info.add_row("🔗", "URL:", url)
    info.add_row("🚌", "MCP:", f"{url}{PROTOCOL_ROUTE_MCP}")
    info.add_row("📚", "FastAPI:", Text(_version("fastapi"), style="dim"))
    info.add_row("📚", "FastMCP:", Text(_version("fastmcp"), style="dim"))
    info.add_row("🚀", "AxonX:", Text(get_build_info().version, style="dim"))

    panel = Panel(
        Group(logo, info),
        title=app_config.app_name,
        title_align="left",
        border_style="dim",
        padding=(1, 4),
        expand=False,
    )
    Console().print(Group("\n", panel, "\n"))


def _json_default(value: object) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def print_json(value: object) -> None:
    """Print one CLI value as readable JSON."""
    print(json.dumps(value, ensure_ascii=False, default=_json_default))


def _event_blocks(event: JobEvent) -> list[tuple[str, object]]:
    """Split one event into labelled blocks without dropping message fields."""
    if not isinstance(event, BackendEvent):
        return [(type(event).__name__, event.model_dump(mode="json"))]

    message = dict(event.message)
    content = message.pop("content", None)
    if event.type_name == "StreamEvent":
        sdk_event = message.get("event") or {}
        event_type = (
            sdk_event.get("type", "unknown")
            if isinstance(sdk_event, dict)
            else "unknown"
        )
        delta = sdk_event.get("delta") if isinstance(sdk_event, dict) else None
        delta_type = delta.get("type") if isinstance(delta, dict) else None
        suffix = f" / {delta_type}" if delta_type else ""
        return [(f"Backend / StreamEvent / {event_type}{suffix}", event.message)]

    blocks: list[tuple[str, object]] = []
    if message:
        blocks.append((f"Backend / {event.type_name} / Metadata", message))
    if isinstance(content, list):
        for block in content:
            block_type = (
                block.get("type_name", "UnknownBlock")
                if isinstance(block, dict)
                else type(block).__name__
            )
            blocks.append((f"Backend / {event.type_name} / {block_type}", block))
    elif content is not None:
        blocks.append((f"Backend / {event.type_name} / Content", content))
    return blocks or [(f"Backend / {event.type_name}", event.message)]


def print_event_blocks(event: JobEvent) -> None:
    """Print every event block immediately with an explicit type marker."""
    for label, payload in _event_blocks(event):
        print(f"\n===== BLOCK: {label} =====", flush=True)
        print(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            flush=True,
        )
