"""Startup logo tests."""

# pylint: disable=missing-function-docstring

from io import StringIO
from types import SimpleNamespace

from rich.console import Console

from axonx.schema import ApplicationConfig
from axonx.utils import logo_utils


def test_logo_shows_effective_http_endpoints(monkeypatch):
    output = StringIO()
    monkeypatch.setattr(
        logo_utils,
        "Console",
        lambda: Console(file=output, force_terminal=False, width=120),
    )

    logo_utils.print_logo(
        ApplicationConfig(app_name="Trading Axon"),
        SimpleNamespace(host="0.0.0.0", port=8123),
    )

    rendered = output.getvalue()
    assert "Trading Axon" in rendered
    assert "http://0.0.0.0:8123" in rendered
    assert "http://0.0.0.0:8123/mcp" in rendered
    assert "AxonX:" in rendered
