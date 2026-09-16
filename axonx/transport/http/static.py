"""Optional Studio static site mounting."""

from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def resolve_web_static_dir(configured_dir: str | None) -> Path | None:
    """Find a usable Studio build, favoring an explicit directory."""
    candidates = []
    if configured_dir:
        candidates.append(Path(configured_dir).expanduser())
    candidates.extend(
        (
            Path(__file__).resolve().parents[3] / "axonx_studio" / "dist",
            Path(__file__).resolve().parents[2] / "static",
        ),
    )
    for candidate in candidates:
        resolved = candidate.resolve()
        if (resolved / "index.html").is_file():
            return resolved
    return None


def mount_web_app(server, static_root: Path) -> None:
    """Mount assets and the SPA fallback after API and Job routes."""
    assets_dir = static_root / "assets"
    if assets_dir.is_dir():
        server.mount("/assets", StaticFiles(directory=str(assets_dir)), name="web-assets")
    index_file = static_root / "index.html"
    no_cache_headers = {"Cache-Control": "no-cache, no-store, must-revalidate"}

    @server.get("/{full_path:path}", include_in_schema=False)
    async def studio_spa(full_path: str):
        if full_path in {"docs", "redoc", "openapi.json"}:
            raise HTTPException(status_code=404, detail="Not Found")
        if full_path and not Path(full_path).is_absolute():
            static_file = (static_root / full_path).resolve()
            if static_file.is_relative_to(static_root) and static_file.is_file():
                return FileResponse(static_file)
        return FileResponse(index_file, headers=no_cache_headers)
