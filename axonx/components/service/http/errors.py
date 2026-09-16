"""Map HTTP use-case errors to the existing response contract."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class HttpUseCaseError(Exception):
    """Expected failure while serving a request."""


class UnknownJobError(HttpUseCaseError):
    pass


class InvalidArgumentsError(HttpUseCaseError):
    pass


class PluginUnavailableError(HttpUseCaseError):
    pass


class PluginAuthenticationError(HttpUseCaseError):
    pass


class PluginDisabledError(HttpUseCaseError):
    pass


class PluginSizeError(HttpUseCaseError):
    pass


class PluginArtifactError(HttpUseCaseError):
    pass


STATUS_CODES = {
    UnknownJobError: 404,
    InvalidArgumentsError: 422,
    PluginUnavailableError: 404,
    PluginAuthenticationError: 401,
    PluginDisabledError: 403,
    PluginSizeError: 413,
    PluginArtifactError: 422,
}


def install_error_handler(server: FastAPI) -> None:
    """Keep all expected HTTP error responses in one place."""

    @server.exception_handler(HttpUseCaseError)
    async def handle_error(_request: Request, exc: HttpUseCaseError) -> JSONResponse:
        return JSONResponse(status_code=STATUS_CODES[type(exc)], content={"detail": str(exc)})
