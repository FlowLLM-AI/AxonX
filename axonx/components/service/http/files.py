"""Workspace file copy HTTP adapter."""

from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException
from starlette.requests import Request

from ....constants import (
    PROTOCOL_FILE_DIRECTORY_HEADER,
    PROTOCOL_FILE_NAME_HEADER,
    PROTOCOL_ROUTE_FILES,
)
from ....utils import format_log_arguments
from ....workspace.models import FileCopy
from ...job.contracts import JobResponse


def create_files_router(service, staged_files) -> APIRouter:
    """Copy uploaded bytes into the workspace copy directory."""
    router = APIRouter()

    @router.post(PROTOCOL_ROUTE_FILES)
    async def copy_file(request: Request):
        filename = request.headers.get(PROTOCOL_FILE_NAME_HEADER, "")
        directory = (
            request.headers.get(PROTOCOL_FILE_DIRECTORY_HEADER, "").strip() or None
        )
        arguments = format_log_arguments(
            {
                "filename": filename,
                "directory": directory or "",
                "content_length": request.headers.get("content-length", ""),
            },
        )
        service.logger.info(
            f"File endpoint called: name=copy_file arguments={arguments}"
        )
        _check_upload_size(request, staged_files.max_upload_bytes)
        copied = await _copy_request(staged_files, request, filename, directory)
        return JobResponse(
            answer=FileCopy(path=copied.path, sha256=copied.sha256, size=copied.size)
        )

    @router.delete(PROTOCOL_ROUTE_FILES)
    async def discard_file(path: str):
        """Discard one staged upload; repeated cleanup is intentionally harmless."""
        try:
            discarded = staged_files.discard(path)
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from exc
        return JobResponse(answer={"path": discarded})

    return router


def _check_upload_size(request: Request, limit: int) -> None:
    """Reject an upload whose declared size already exceeds the limit."""
    declared = request.headers.get("content-length")
    if not declared:
        return
    try:
        size = int(declared)
    except ValueError as exc:
        raise HTTPException(400, "Invalid Content-Length header") from exc
    if size < 0:
        raise HTTPException(400, "Invalid Content-Length header")
    if size > limit:
        raise HTTPException(
            413, f"Upload exceeds the configured limit of {limit} bytes"
        )


async def _copy_request(
    staged_files, request: Request, filename: str, directory: str | None
):
    """Stream one request body into the configured workspace."""
    limit = staged_files.max_upload_bytes
    written = 0

    async def chunks() -> AsyncIterator[bytes]:
        nonlocal written
        async for chunk in request.stream():
            written += len(chunk)
            if written > limit:
                raise HTTPException(
                    413, f"Upload exceeds the configured limit of {limit} bytes"
                )
            yield chunk

    try:
        return await staged_files.store_stream(chunks(), filename, directory)
    except FileExistsError as exc:
        raise HTTPException(409, str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
