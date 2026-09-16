"""Plugin upload HTTP adapter."""

import asyncio
import hmac
from typing import TYPE_CHECKING, cast

from fastapi import APIRouter
from starlette.requests import Request

from ....utils import format_log_arguments
from .errors import (
    PluginArtifactError,
    PluginAuthenticationError,
    PluginDisabledError,
    PluginSizeError,
    PluginUnavailableError,
)

if TYPE_CHECKING:
    from ...plugin.base import BasePluginComponent


def create_plugins_router(app, logger) -> APIRouter:
    """Expose wheel upload while retaining its existing error responses."""
    router = APIRouter()

    @router.post("/plugins")
    async def install_plugin(request: Request):
        arguments = format_log_arguments(
            {
                "filename": request.headers.get("x-wheel-filename", ""),
                "sha256": request.headers.get("x-wheel-sha256", ""),
                "content_length": request.headers.get("content-length", ""),
            },
        )
        logger.info(f"Plugin endpoint called: name=install_plugin arguments={arguments}")
        plugins = app.context.components.get("plugin", {})
        plugin = cast("BasePluginComponent | None", next(iter(plugins.values()), None))
        if plugin is None:
            raise PluginUnavailableError("Plugin component is not configured")
        if not plugin.allow_remote_install:
            raise PluginDisabledError("Remote plugin installation is disabled")
        authorization = request.headers.get("authorization", "")
        if plugin.install_token and not hmac.compare_digest(
            authorization,
            f"Bearer {plugin.install_token}",
        ):
            raise PluginAuthenticationError("Invalid plugin installation token")
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > plugin.max_wheel_bytes:
            raise PluginSizeError("Wheel exceeds configured size limit")
        data = await request.body()
        try:
            artifact = await asyncio.to_thread(
                plugin.install_wheel,
                data,
                request.headers.get("x-wheel-sha256", ""),
                request.headers.get("x-wheel-filename", ""),
            )
        except (RuntimeError, TypeError, ValueError) as exc:
            raise PluginArtifactError(str(exc)) from exc
        return {
            "installed": True,
            "distribution": artifact.distribution,
            "version": artifact.version,
            "plugins": artifact.plugin_names,
            **artifact.contributions_dict(),
            "restart_required": bool(artifact.components or artifact.jobs),
            "sha256": artifact.sha256,
        }

    return router
