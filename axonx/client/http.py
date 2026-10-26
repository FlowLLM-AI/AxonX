"""Client for the complete AxonX HTTP protocol."""

import json
import os
from collections.abc import AsyncIterator, Mapping
from contextlib import aclosing
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from ..utils.async_work import run_blocking
from .base import BaseClient, RemoteConnectionError, RemoteServiceError
from .config import (
    AXONX_CLI_REQUEST_ID,
    AXONX_DEFAULT_REQUEST_TIMEOUT,
    PROTOCOL_AUTH_HEADER,
    PROTOCOL_AUTH_SCHEME,
    PROTOCOL_CLI_REQUEST_HEADER,
    PROTOCOL_FILE_DIRECTORY_HEADER,
    PROTOCOL_FILE_NAME_HEADER,
    PROTOCOL_ROUTE_HEALTH,
    PROTOCOL_ROUTE_JOB,
    PROTOCOL_ROUTE_JOB_EVENTS,
    PROTOCOL_ROUTE_JOBS,
    PROTOCOL_ROUTE_UPLOAD,
    PROTOCOL_SSE_DATA_PREFIX,
    PROTOCOL_SSE_MEDIA_TYPE,
)
from .events import JOB_EVENT_ADAPTER, JobEvent, ResultEvent
from .models import JobCatalog, JobInfo, JobResponse, StagedFile

_UPLOAD_CHUNK_BYTES = 1024 * 1024


async def _file_chunks(path: Path) -> AsyncIterator[bytes]:
    """Read a file without blocking the event loop or buffering it in memory."""
    with path.open("rb") as stream:
        while chunk := await run_blocking(stream.read, _UPLOAD_CHUNK_BYTES):
            yield chunk


def _error_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return f"HTTP {response.status_code}"
    detail = body.get("detail") if isinstance(body, dict) else None
    if detail in (None, ""):
        return f"HTTP {response.status_code}"
    return detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False)


class HttpClient(BaseClient[httpx.AsyncClient]):
    """Call Jobs, consume event streams, and copy files through HTTP."""

    def __init__(
        self,
        *,
        target: str | None = None,
        timeout: float = AXONX_DEFAULT_REQUEST_TIMEOUT,
        token: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(target=target, timeout=timeout, token=token)
        self._transport = transport

    async def _connect(self) -> httpx.AsyncClient:
        headers = {PROTOCOL_AUTH_HEADER: f"{PROTOCOL_AUTH_SCHEME} {self.token}"} if self.token else {}
        if request_id := os.environ.get(AXONX_CLI_REQUEST_ID):
            headers[PROTOCOL_CLI_REQUEST_HEADER] = request_id
        return httpx.AsyncClient(
            base_url=self.target,
            timeout=self.timeout,
            transport=self._transport,
            headers=headers,
        )

    async def _disconnect(self, client: httpx.AsyncClient) -> None:
        await client.aclose()

    def _transport_error(self, operation: str, endpoint: str, exc: httpx.HTTPError) -> RemoteServiceError:
        # Exception messages can be empty (notably ReadTimeout). Never include headers or arguments.
        detail = str(exc) or "no additional detail"
        error = (
            RemoteConnectionError
            if isinstance(exc, (httpx.NetworkError, httpx.TimeoutException))
            else RemoteServiceError
        )
        return error(
            f"Remote {operation} failed: {type(exc).__name__} "
            f"(target={self.target}, endpoint={endpoint}, timeout={self.timeout:g}s): {detail}"
        )

    async def _response(self, method: str, endpoint: str, **request) -> JobResponse:
        try:
            response = await self._require_client().request(method, endpoint, **request)
        except httpx.HTTPError as exc:
            raise self._transport_error("request", endpoint, exc) from exc
        self._check_status(response)
        try:
            payload = response.json()
        except ValueError as exc:
            raise RemoteServiceError("Remote service returned an invalid response envelope") from exc
        return self._parse_payload(payload, JobResponse)

    @staticmethod
    def _check_status(response: httpx.Response) -> None:
        if not response.is_success:
            raise RemoteServiceError(
                f"Remote request was rejected: {_error_detail(response)}",
                status_code=response.status_code,
            )

    async def run_job(self, name: str, arguments: Mapping[str, Any] | None = None) -> JobResponse:
        return await self._response(
            "POST",
            PROTOCOL_ROUTE_JOB.format(name=quote(name, safe="")),
            json={"arguments": dict(arguments or {})},
        )

    async def stream_job(
        self,
        name: str,
        arguments: Mapping[str, Any] | None = None,
    ) -> AsyncIterator[JobEvent]:
        """Decode one Job's Server-Sent Events without buffering its response."""
        endpoint = PROTOCOL_ROUTE_JOB_EVENTS.format(name=quote(name, safe=""))
        try:
            async with self._require_client().stream(
                "POST",
                endpoint,
                json={"arguments": dict(arguments or {})},
                headers={"accept": PROTOCOL_SSE_MEDIA_TYPE},
            ) as response:
                if not response.is_success:
                    await response.aread()
                    self._check_status(response)
                media_type = response.headers.get("content-type", "").partition(";")[0].strip().lower()
                if media_type != PROTOCOL_SSE_MEDIA_TYPE:
                    raise RemoteServiceError("Remote service returned a non-event stream response")
                async for line in response.aiter_lines():
                    if line.startswith(PROTOCOL_SSE_DATA_PREFIX):
                        try:
                            payload = json.loads(line[len(PROTOCOL_SSE_DATA_PREFIX) :])
                            event = JOB_EVENT_ADAPTER.validate_python(payload, strict=True)
                            if isinstance(event, ResultEvent):
                                self._parse_payload(payload, ResultEvent)
                        except ValueError as exc:
                            raise RemoteServiceError("Remote service returned an invalid stream event") from exc
                        yield event
                        if isinstance(event, ResultEvent):
                            return
                raise RemoteServiceError("Remote event stream ended without a terminal result")
        except httpx.HTTPError as exc:
            raise self._transport_error("stream", endpoint, exc) from exc

    async def list_jobs(self) -> list[JobInfo]:
        response = await self._response("GET", PROTOCOL_ROUTE_JOBS)
        return self._parse_payload(response.answer, JobCatalog).items

    async def health(self) -> bool:
        self._require_client()
        try:
            response = await self._response("GET", PROTOCOL_ROUTE_HEALTH)
        except RemoteServiceError:
            return False
        return response.success and isinstance(response.answer, dict) and response.answer.get("running") is True

    async def copy_file(
        self,
        path: Path,
        *,
        filename: str | None = None,
        directory: str | None = None,
    ) -> StagedFile:
        """Copy one local file into the remote workspace."""
        size = path.stat().st_size
        headers = {
            "content-type": "application/octet-stream",
            "content-length": str(size),
            PROTOCOL_FILE_NAME_HEADER: filename or path.name,
        }
        if directory:
            headers[PROTOCOL_FILE_DIRECTORY_HEADER] = directory
        response = await self._response("POST", PROTOCOL_ROUTE_UPLOAD, content=_file_chunks(path), headers=headers)
        return self._parse_payload(response.answer, StagedFile)

    async def discard_file(self, path: str) -> str:
        """Discard one staged remote file, including an already-consumed one."""
        response = await self._response("DELETE", PROTOCOL_ROUTE_UPLOAD, params={"path": path})
        answer = response.answer
        if not isinstance(answer, dict) or not isinstance(answer.get("path"), str):
            raise RemoteServiceError("Remote service returned an invalid file cleanup payload")
        return answer["path"]


async def run_remote_job(
    name: str,
    arguments: Mapping[str, Any],
    **client_options,
) -> JobResponse:
    """Invoke one Job through a freshly connected HTTP client."""
    async with HttpClient(**client_options) as client:
        return await client.run_job(name, arguments)


async def stream_remote_job(
    name: str,
    arguments: Mapping[str, Any],
    **client_options,
) -> AsyncIterator[JobEvent]:
    """Stream one Job through a freshly connected HTTP client."""
    async with HttpClient(**client_options) as client:
        async with aclosing(client.stream_job(name, arguments)) as events:
            async for event in events:
                yield event
