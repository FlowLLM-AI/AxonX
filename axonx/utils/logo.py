"""Startup banner with AxonX runtime metadata."""

import colorsys
import importlib.metadata
import random
from typing import TYPE_CHECKING

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..constants import AXONX_DEFAULT_BIND_HOST, AXONX_DEFAULT_PORT

if TYPE_CHECKING:
    from ..components.service import HttpService
    from ..schema import ApplicationConfig


def _version(package_name: str) -> str:
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return ""


def _rgb(hue: float) -> tuple[int, int, int]:
    red, green, blue = colorsys.hsv_to_rgb(hue % 1.0, 0.85, 0.98)
    return int(red * 255), int(green * 255), int(blue * 255)


def print_logo(app_config: "ApplicationConfig", service: "HttpService") -> None:
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

    host = getattr(service, "host", AXONX_DEFAULT_BIND_HOST)
    port = getattr(service, "port", AXONX_DEFAULT_PORT)
    display_host = "127.0.0.1" if host == "0.0.0.0" else host
    url = f"http://{display_host}:{port}"
    info = Table.grid(padding=(0, 1))
    info.add_column(style="bold", justify="center")
    info.add_column(style="bold cyan")
    info.add_column(style="white")
    info.add_row("📦", "Backend:", "http")
    info.add_row("🔗", "URL:", url)
    info.add_row("🚌", "MCP:", f"{url}/mcp")
    info.add_row("📚", "FastAPI:", Text(_version("fastapi"), style="dim"))
    info.add_row("📚", "FastMCP:", Text(_version("fastmcp"), style="dim"))
    info.add_row("🚀", "AxonX:", Text(_version("axonx"), style="dim"))

    panel = Panel(
        Group(logo, info),
        title=app_config.app_name,
        title_align="left",
        border_style="dim",
        padding=(1, 4),
        expand=False,
    )
    Console().print(Group("\n", panel, "\n"))
