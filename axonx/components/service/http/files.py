"""Stage raw binary or multipart file uploads through the same HTTP endpoint."""

from collections.abc import AsyncIterator

from anyio import CancelScope
from fastapi import APIRouter, HTTPException
from python_multipart.exceptions import MultipartParseError
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser
from starlette.requests import Request

from ....constants import (
    PROTOCOL_FILE_DIRECTORY_HEADER,
    PROTOCOL_FILE_NAME_HEADER,
    PROTOCOL_ROUTE_FILES,
)
from ....utils import format_log_arguments
from ....workspace.models import FileCopy
from ...job.contracts import JobResponse

# Allow a bounded amount of multipart framing in addition to the file byte limit.
MULTIPART_OVERHEAD_BYTES = 64 * 1024
UPLOAD_CHUNK_BYTES = 64 * 1024


def create_files_router(service, staged_files) -> APIRouter:
    """Copy uploaded bytes into the workspace copy directory."""
    router = APIRouter()

    @router.post(
        PROTOCOL_ROUTE_FILES,
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    "application/octet-stream": {"schema": {"type": "string", "format": "binary"}},
                    "multipart/form-data": {
                        "schema": {
                            "type": "object",
                            "required": ["file"],
                            "properties": {
                                "file": {"type": "string", "format": "binary"},
                                "directory": {"type": "string", "description": "Staging directory under tmp."},
                            },
                            "additionalProperties": False,
                        },
                    },
                },
            },
        },
    )
    async def copy_file(request: Request):
        """Upload one file; headers override multipart filename and directory."""
        filename = request.headers.get(PROTOCOL_FILE_NAME_HEADER, "")
        directory = request.headers.get(PROTOCOL_FILE_DIRECTORY_HEADER, "").strip() or None
        arguments = format_log_arguments(
            {
                "filename": filename,
                "directory": directory or "",
                "content_length": request.headers.get("content-length", ""),
            },
        )
        service.logger.info(f"File endpoint called: name=copy_file arguments={arguments}")
        content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        multipart = content_type == "multipart/form-data"
        body_limit = staged_files.max_upload_bytes + (MULTIPART_OVERHEAD_BYTES if multipart else 0)
        _check_upload_size(request, body_limit)
        try:
            if multipart:
                copied = await _copy_multipart(staged_files, request, filename, directory)
            else:
                copied = await staged_files.store_stream(_request_chunks(request, body_limit), filename, directory)
        except FileExistsError as exc:
            raise HTTPException(409, str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from exc
        return JobResponse(answer=FileCopy(path=copied.path, sha256=copied.sha256, size=copied.size))

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
        raise HTTPException(413, f"Upload exceeds the configured limit of {limit} bytes")


async def _request_chunks(request: Request, limit: int) -> AsyncIterator[bytes]:
    """Bound incoming bytes even when Content-Length is missing or inaccurate."""
    written = 0
    async for chunk in request.stream():
        written += len(chunk)
        if written > limit:
            raise HTTPException(413, f"Upload exceeds the configured request limit of {limit} bytes")
        yield chunk


class _UploadParser(MultiPartParser):
    """Bound file bytes during parsing and close partial spools on every failure."""

    def __init__(self, request: Request, limit: int):
        super().__init__(
            request.headers,
            _request_chunks(request, limit + MULTIPART_OVERHEAD_BYTES),
            max_files=1,
            max_fields=1,
            max_part_size=MULTIPART_OVERHEAD_BYTES,
        )
        self.file_limit = limit
        self.file_bytes = 0
        self.complete = False

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        if self._current_part.file is not None:
            self.file_bytes += end - start
            if self.file_bytes > self.file_limit:
                raise HTTPException(413, f"Upload exceeds the configured limit of {self.file_limit} bytes")
        super().on_part_data(data, start, end)

    def on_end(self) -> None:
        self.complete = True

    async def parse(self):
        form = await super().parse()
        if not self.complete:
            # Starlette closes spools on parser failures; this check happens after parsing.
            for temporary in self._files_to_close_on_error:
                temporary.close()
            raise MultiPartException("Incomplete multipart body")
        return form


async def _copy_multipart(staged_files, request: Request, filename: str, directory: str | None):
    """Parse one file and optional directory, then reuse content-addressed storage."""
    try:
        form = await _UploadParser(request, staged_files.max_upload_bytes).parse()
    except (MultiPartException, MultipartParseError) as exc:
        raise HTTPException(400, str(exc)) from exc

    try:
        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            raise HTTPException(422, "Multipart upload requires one file field named 'file'")
        if len(form.multi_items()) != len(form):
            raise HTTPException(422, "Duplicate multipart fields are not supported")
        if any(key not in {"file", "directory"} for key in form):
            raise HTTPException(422, "Only 'file' and 'directory' multipart fields are supported")
        form_directory = form.get("directory", "")

        async def chunks() -> AsyncIterator[bytes]:
            while chunk := await upload.read(UPLOAD_CHUNK_BYTES):
                yield chunk

        return await staged_files.store_stream(
            chunks(), filename or upload.filename or "", directory or form_directory.strip() or None
        )
    finally:
        # Rolled spools close in a worker thread, so cleanup must survive cancellation.
        with CancelScope(shield=True):
            await form.close()
