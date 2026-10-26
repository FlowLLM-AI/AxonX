"""Transport-independent remote client lifecycle."""

import asyncio
import os
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any

from ...async_work import complete_on_cancel
from ...connection import ConnectionOptions, default_target
from ...constants import AXONX_DEFAULT_REQUEST_TIMEOUT
from ...protocol import AXONX_SERVICE_TARGET
from ..job.models import JobInfo, JobResponse


class RemoteServiceError(RuntimeError):
    """A remote request failed or returned an invalid protocol response."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class BaseClient[ClientT](ABC):
    """Own one connection to an AxonX service transport."""

    url_path = ""

    def __init__(
        self,
        *,
        target: str | None = None,
        timeout: float = AXONX_DEFAULT_REQUEST_TIMEOUT,
        token: str | None = None,
    ) -> None:
        options = ConnectionOptions(
            target=target if target is not None else os.environ.get(AXONX_SERVICE_TARGET, default_target()),
            timeout=timeout,
            token=token,
        )
        self.target = options.target
        self.url = f"{self.target}{self.url_path}"
        self.timeout = options.timeout
        self.token = options.token
        self._client: ClientT | None = None
        self._lifecycle_lock = asyncio.Lock()

    @property
    def is_started(self) -> bool:
        return self._client is not None

    async def start(self) -> None:
        """Open one connection; concurrent starts share it."""
        async with self._lifecycle_lock:
            if self._client is None:
                self._client = await self._connect()

    async def close(self) -> None:
        """Finish closing the owned connection before propagating cancellation."""
        async with self._lifecycle_lock:
            client, self._client = self._client, None
            if client is not None:
                await complete_on_cancel(self._disconnect(client))

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *_):
        await self.close()

    def _require_client(self) -> ClientT:
        if self._client is None:
            raise RuntimeError("Client is not started")
        return self._client

    @staticmethod
    def _parse_response(payload: Any) -> JobResponse:
        try:
            response = JobResponse.model_validate(payload, strict=True)
            if response.model_fields_set != JobResponse.model_fields.keys():
                raise ValueError("Incomplete JobResponse envelope")
        except ValueError as exc:
            raise RemoteServiceError("Remote service returned an invalid response envelope") from exc
        return response

    @abstractmethod
    async def _connect(self) -> ClientT:
        """Open the concrete transport connection."""

    @abstractmethod
    async def _disconnect(self, client: ClientT) -> None:
        """Close the concrete transport connection."""

    @abstractmethod
    async def run_job(
        self,
        name: str,
        arguments: Mapping | None = None,
    ) -> JobResponse:
        """Invoke one remote Job."""

    @abstractmethod
    async def list_jobs(self) -> list[JobInfo]:
        """List remotely exposed Jobs."""

    @abstractmethod
    async def health(self) -> bool:
        """Return whether the remote service is healthy."""
