"""Startup banner with AxonX runtime metadata."""

from __future__ import annotations

import colorsys
import random
from typing import TYPE_CHECKING

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ...client.config import (
    AXONX_DEFAULT_CONNECT_HOST,
    AXONX_DEFAULT_PORT,
    AXONX_DEFAULT_SCHEME,
    PROTOCOL_ROUTE_MCP,
)
from ..components.machine.build_info import get_build_info, package_version

if TYPE_CHECKING:
    from ..components.service.base import BaseService
    from ..config.models import ApplicationConfig


def _rgb(hue: float) -> tuple[int, int, int]:
    red, green, blue = colorsys.hsv_to_rgb(hue % 1.0, 0.85, 0.98)
    return int(red * 255), int(green * 255), int(blue * 255)


def print_logo(app_config: ApplicationConfig, service: BaseService, *, console: Console | None = None) -> None:
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
            red, green, blue = _rgb(hue_base + line_number * 0.08 + position / max(1, len(line) - 1) * 0.5)
            logo.append(character, style=f"bold rgb({red},{green},{blue})")
        logo.append("\n")

    host = getattr(service, "host", app_config.bind_host)
    port = getattr(service, "port", AXONX_DEFAULT_PORT)
    display_host = AXONX_DEFAULT_CONNECT_HOST if host == "0.0.0.0" else host
    display_host = f"[{display_host}]" if ":" in display_host else display_host
    url = f"{AXONX_DEFAULT_SCHEME}://{display_host}:{port}"
    info = Table.grid(padding=(0, 1))
    info.add_column(style="bold", justify="center")
    info.add_column(style="bold cyan")
    info.add_column(style="white")
    info.add_row("📦", "Backend:", service.backend)
    info.add_row("🔗", "URL:", url)
    info.add_row("🚌", "MCP:", f"{url}{PROTOCOL_ROUTE_MCP}")
    info.add_row("📚", "FastAPI:", Text(package_version("fastapi") or "", style="dim"))
    info.add_row("📚", "FastMCP:", Text(package_version("fastmcp") or "", style="dim"))
    info.add_row("🚀", "AxonX:", Text(get_build_info().version, style="dim"))

    panel = Panel(
        Group(logo, info),
        title=app_config.app_name,
        title_align="left",
        border_style="dim",
        padding=(1, 4),
        expand=False,
    )
    (console or Console()).print(Group("\n", panel, "\n"))
