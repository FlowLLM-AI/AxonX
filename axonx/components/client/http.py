"""Client for the complete AxonX HTTP protocol."""

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TypeVar
from urllib.parse import quote

import httpx
from pydantic import BaseModel, ValidationError

from ...constants import (
    AXONX_DEFAULT_REQUEST_TIMEOUT,
    PROTOCOL_AUTH_HEADER,
    PROTOCOL_AUTH_SCHEME,
    PROTOCOL_FILE_DIRECTORY_HEADER,
    PROTOCOL_FILE_NAME_HEADER,
    PROTOCOL_ROUTE_FILES,
    PROTOCOL_ROUTE_HEALTH,
    PROTOCOL_ROUTE_JOB,
    PROTOCOL_ROUTE_JOB_EVENTS,
    PROTOCOL_ROUTE_JOBS,
    PROTOCOL_SSE_DATA_PREFIX,
    PROTOCOL_SSE_MEDIA_TYPE,
    REMOTE_IP_ARGUMENT,
)
from ...workspace.models import FileCopy
from ..job.base import (
    JOB_EVENT_ADAPTER,
    JobCatalog,
    JobEvent,
    JobInfo,
    JobResponse,
    ResultEvent,
)
from .base import BaseClient, RemoteServiceError

_UPLOAD_CHUNK_BYTES = 1024 * 1024
PayloadT = TypeVar("PayloadT", bound=BaseModel)


async def _file_chunks(path: Path) -> AsyncIterator[bytes]:
    """Read a file without blocking the event loop or buffering it in memory."""
    with path.open("rb") as stream:
        while chunk := await asyncio.to_thread(stream.read, _UPLOAD_CHUNK_BYTES):
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
        host_ip: str | None = None,
        host_port: int | None = None,
        timeout: float = AXONX_DEFAULT_REQUEST_TIMEOUT,
        token: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        **kwargs,
    ) -> None:
        super().__init__(
            host_ip=host_ip, host_port=host_port, timeout=timeout, token=token, **kwargs
        )
        self._transport = transport

    async def _connect(self) -> httpx.AsyncClient:
        headers = (
            {PROTOCOL_AUTH_HEADER: f"{PROTOCOL_AUTH_SCHEME} {self.token}"}
            if self.token
            else None
        )
        return httpx.AsyncClient(
            base_url=self.url,
            timeout=self.timeout,
            transport=self._transport,
            headers=headers,
        )

    async def _disconnect(self, client: httpx.AsyncClient) -> None:
        await client.aclose()

    async def _response(self, method: str, endpoint: str, **request) -> JobResponse:
        try:
            response = await self._require_client().request(method, endpoint, **request)
        except httpx.HTTPError as exc:
            raise RemoteServiceError(f"Remote request failed: {exc}") from exc
        if not response.is_success:
            raise RemoteServiceError(
                f"Remote request was rejected: {_error_detail(response)}",
                status_code=response.status_code,
            )
        try:
            return JobResponse.model_validate_json(response.content)
        except ValidationError as exc:
            raise RemoteServiceError(
                "Remote service returned an invalid response envelope"
            ) from exc

    @staticmethod
    def _payload(response: JobResponse, model: type[PayloadT]) -> PayloadT:
        try:
            return model.model_validate(response.answer)
        except ValidationError as exc:
            raise RemoteServiceError(
                f"Remote service returned an invalid {model.__name__} payload"
            ) from exc

    async def run_job(
        self, name: str, arguments=None, *, remote_ip: str | None = None
    ) -> JobResponse:
        return await self._response(
            "POST",
            PROTOCOL_ROUTE_JOB.format(name=quote(name, safe="")),
            json={"arguments": dict(arguments or {}), REMOTE_IP_ARGUMENT: remote_ip},
        )

    async def stream_job(
        self,
        name: str,
        arguments=None,
        *,
        remote_ip: str | None = None,
    ) -> AsyncIterator[JobEvent]:
        """Decode one Job's Server-Sent Events without buffering its response."""
        endpoint = PROTOCOL_ROUTE_JOB_EVENTS.format(name=quote(name, safe=""))
        try:
            async with self._require_client().stream(
                "POST",
                endpoint,
                json={
                    "arguments": dict(arguments or {}),
                    REMOTE_IP_ARGUMENT: remote_ip,
                },
                headers={"accept": PROTOCOL_SSE_MEDIA_TYPE},
            ) as response:
                if not response.is_success:
                    await response.aread()
                    raise RemoteServiceError(
                        f"Remote request was rejected: {_error_detail(response)}",
                        status_code=response.status_code,
                    )
                if not response.headers.get("content-type", "").startswith(
                    PROTOCOL_SSE_MEDIA_TYPE
                ):
                    raise RemoteServiceError(
                        "Remote service returned a non-event stream response"
                    )
                async for line in response.aiter_lines():
                    if line.startswith(PROTOCOL_SSE_DATA_PREFIX):
                        try:
                            event = JOB_EVENT_ADAPTER.validate_json(
                                line[len(PROTOCOL_SSE_DATA_PREFIX) :]
                            )
                        except ValidationError as exc:
                            raise RemoteServiceError(
                                "Remote service returned an invalid stream event"
                            ) from exc
                        yield event
                        if isinstance(event, ResultEvent):
                            return
                raise RemoteServiceError(
                    "Remote event stream ended without a terminal result"
                )
        except httpx.HTTPError as exc:
            raise RemoteServiceError(f"Remote stream failed: {exc}") from exc

    async def list_jobs(self) -> list[JobInfo]:
        response = await self._response("GET", PROTOCOL_ROUTE_JOBS)
        return self._payload(response, JobCatalog).items

    async def health(self) -> bool:
        try:
            response = await self._response("GET", PROTOCOL_ROUTE_HEALTH)
        except RemoteServiceError:
            return False
        return (
            isinstance(response.answer, dict) and response.answer.get("running") is True
        )

    async def copy_file(
        self,
        path: Path,
        *,
        filename: str | None = None,
        directory: str | None = None,
    ) -> FileCopy:
        """Copy one local file into the remote workspace."""
        size = path.stat().st_size
        headers = {
            "content-type": "application/octet-stream",
            "content-length": str(size),
            PROTOCOL_FILE_NAME_HEADER: filename or path.name,
        }
        if directory:
            headers[PROTOCOL_FILE_DIRECTORY_HEADER] = directory
        response = await self._response(
            "POST", PROTOCOL_ROUTE_FILES, content=_file_chunks(path), headers=headers
        )
        return self._payload(response, FileCopy)

    async def discard_file(self, path: str) -> str:
        """Discard one staged remote file, including an already-consumed one."""
        response = await self._response(
            "DELETE", PROTOCOL_ROUTE_FILES, params={"path": path}
        )
        answer = response.answer
        if not isinstance(answer, dict) or not isinstance(answer.get("path"), str):
            raise RemoteServiceError(
                "Remote service returned an invalid file cleanup payload"
            )
        return answer["path"]
