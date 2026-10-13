"""Exercise optional packaged Studio hosting and API coexistence."""

import sys
import shutil

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import axonx_studio
from axonx.components.service.http.studio import mount_studio, resolve_studio_dir


@pytest.mark.parametrize("resource", ["index", "assets_before_request", "assets_after_request", "dist"])
def test_removed_studio_resources_leave_api_available(tmp_path, resource):
    """Deleted builds produce controlled errors and can be restored in place."""
    index = tmp_path / "index.html"
    index.write_text("Studio", encoding="utf-8")
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("studio", encoding="utf-8")
    server = FastAPI()

    @server.get("/health")
    def health():
        return {"healthy": True}

    mount_studio(server, tmp_path)
    with TestClient(server) as client:
        assert client.get("/").status_code == 200
        if resource == "assets_after_request":
            assert client.get("/assets/app.js").status_code == 200
        if resource == "index":
            index.unlink()
        elif resource == "dist":
            shutil.rmtree(tmp_path)
        else:
            shutil.rmtree(assets)
        for _ in range(2):
            if resource in {"index", "dist"}:
                for path in ("/", "/nested/page"):
                    response = client.get(path)
                    assert response.status_code == 503
                    assert response.headers["cache-control"] == "no-store"
                    assert "API remains available" in response.text
            if resource != "index":
                assert client.get("/assets/app.js").status_code in {404, 503}
            assert client.get("/health").json() == {"healthy": True}
        tmp_path.mkdir(exist_ok=True)
        index.write_text("Restored Studio", encoding="utf-8")
        assets.mkdir(exist_ok=True)
        (assets / "app.js").write_text("restored", encoding="utf-8")
        assert client.get("/").text == "Restored Studio"
        assert client.get("/assets/app.js").text == "restored"


def test_studio_file_removed_before_response_stat(monkeypatch, tmp_path):
    """Cover deletion after routing, where an existence check is insufficient."""
    from fastapi.responses import FileResponse

    index = tmp_path / "index.html"
    index.write_text("Studio", encoding="utf-8")
    server = FastAPI()
    mount_studio(server, tmp_path)
    original = FileResponse.__call__

    async def remove_then_send(self, scope, receive, send):
        index.unlink()
        await original(self, scope, receive, send)

    monkeypatch.setattr(FileResponse, "__call__", remove_then_send)
    with TestClient(server) as client:
        assert client.get("/").status_code == 503


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
