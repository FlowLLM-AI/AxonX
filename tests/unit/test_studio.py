"""Exercise optional packaged Studio hosting and API coexistence."""

import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

import axonx_studio
from axonx.components.service.http.studio import mount_studio, resolve_studio_dir


def test_studio_is_optional(monkeypatch):
    """An absent package leaves API-only installations usable."""
    monkeypatch.setitem(sys.modules, "axonx_studio", None)
    assert resolve_studio_dir() is None


def test_studio_requires_built_assets(monkeypatch, tmp_path):
    """An unbuilt editable package cannot supply a Studio page."""
    monkeypatch.setattr(axonx_studio, "static_dir", lambda: tmp_path)
    assert resolve_studio_dir() is None


def test_packaged_studio_serves_assets_and_spa_without_shadowing_api(monkeypatch, tmp_path):
    """Load the package provider and keep existing API routes authoritative."""
    (tmp_path / "index.html").write_text("<html>Studio</html>", encoding="utf-8")
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("console.log('studio')", encoding="utf-8")
    monkeypatch.setattr(axonx_studio, "static_dir", lambda: tmp_path)
    server = FastAPI()

    @server.get("/health")
    def health():
        return {"healthy": True}

    mount_studio(server, resolve_studio_dir())
    with TestClient(server) as client:
        assert client.get("/health").json() == {"healthy": True}
        assert client.get("/").text == "<html>Studio</html>"
        assert client.get("/nested/page").text == "<html>Studio</html>"
        assert client.get("/assets/app.js").text == "console.log('studio')"
