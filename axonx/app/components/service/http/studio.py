"""Optional Studio static site mounting."""

from pathlib import Path

from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles


async def _serve_studio_resource(app, scope, receive, send) -> None:
    """Handle removed resources before response headers have been sent."""
    started = False

    async def track_start(message):
        nonlocal started
        if message["type"] == "http.response.start":
            started = True
        await send(message)

    try:
        await app(scope, receive, track_start)
    except (FileNotFoundError, NotADirectoryError, RuntimeError) as exc:
        missing = isinstance(exc, (FileNotFoundError, NotADirectoryError)) or isinstance(
            exc.__context__, (FileNotFoundError, NotADirectoryError)
        )
        if started or not missing:
            raise
        response = PlainTextResponse(
            "AxonX Studio assets are unavailable. Restore the Studio build and restart the service. "
            "The API remains available.",
            status_code=503,
            headers={"Cache-Control": "no-store"},
        )
        await response(scope, receive, send)


class _StudioFileResponse(FileResponse):
    async def __call__(self, scope, receive, send) -> None:
        await _serve_studio_resource(super().__call__, scope, receive, send)


class _StudioStaticFiles(StaticFiles):
    async def __call__(self, scope, receive, send) -> None:
        await _serve_studio_resource(super().__call__, scope, receive, send)


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
    static_root = static_root.resolve()
    assets_dir = static_root / "assets"
    if assets_dir.is_dir():
        server.mount("/assets", _StudioStaticFiles(directory=str(assets_dir)), name="web-assets")
    index_file = static_root / "index.html"
    no_cache_headers = {"Cache-Control": "no-cache, no-store, must-revalidate"}

    @server.get("/{full_path:path}", include_in_schema=False)
    async def studio_spa(full_path: str):
        if full_path and not Path(full_path).is_absolute():
            static_file = (static_root / full_path).resolve()
            if static_file.is_relative_to(static_root) and static_file.is_file():
                return _StudioFileResponse(static_file)
        return _StudioFileResponse(index_file, headers=no_cache_headers)
