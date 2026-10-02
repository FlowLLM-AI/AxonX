"""Optional Studio static site mounting."""

from pathlib import Path

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def resolve_studio_dir() -> Path | None:
    """Find static assets provided by the optional Studio package."""
    try:
        from axonx_studio import static_dir
    except ModuleNotFoundError as exc:
        if exc.name != "axonx_studio":
            raise
        return None
    root = static_dir()
    return root if (root / "index.html").is_file() else None


def mount_studio(server, static_root: Path) -> None:
    """Mount assets and the SPA fallback after API and Job routes."""
    assets_dir = static_root / "assets"
    if assets_dir.is_dir():
        server.mount("/assets", StaticFiles(directory=str(assets_dir)), name="web-assets")
    index_file = static_root / "index.html"
    no_cache_headers = {"Cache-Control": "no-cache, no-store, must-revalidate"}

    @server.get("/{full_path:path}", include_in_schema=False)
    async def studio_spa(full_path: str):
        if full_path and not Path(full_path).is_absolute():
            static_file = (static_root / full_path).resolve()
            if static_file.is_relative_to(static_root) and static_file.is_file():
                return FileResponse(static_file)
        return FileResponse(index_file, headers=no_cache_headers)
