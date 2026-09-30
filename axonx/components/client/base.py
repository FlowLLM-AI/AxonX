"""Transport-independent remote client lifecycle."""

import os
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, PositiveFloat, field_validator

from ...constants import (
    AXONX_DEFAULT_REQUEST_TIMEOUT,
    AXONX_SERVICE_TARGET,
)
from ...enums import ComponentEnum
from ...utils.target import default_target, normalize_target
from ..base import BaseComponent
from ..job.contracts import JobInfo, JobResponse


class ClientOptions(BaseModel):
    """Validated options for one remote AxonX connection."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    target: str | None = None
    timeout: PositiveFloat = AXONX_DEFAULT_REQUEST_TIMEOUT
    stream: bool = False
    token: str | None = Field(default=None, min_length=1, repr=False)
    stream_format: Literal["blocks", "json"] = "blocks"

    @field_validator("target")
    @classmethod
    def validate_target(cls, value: str | None) -> str | None:
        return normalize_target(value) if value is not None else None


class RemoteServiceError(RuntimeError):
    """A remote request failed or returned an invalid protocol response."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class BaseClient[ClientT](BaseComponent, ABC):
    """Own one connection to an AxonX service transport."""

    component_type = ComponentEnum.CLIENT
    url_path = ""

    def __init__(
        self,
        *,
        target: str | None = None,
        timeout: float = AXONX_DEFAULT_REQUEST_TIMEOUT,
        token: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        options = ClientOptions(target=target, timeout=timeout, token=token)
        self.target = self._resolve_target(options)
        self.url = f"{self.target}{self.url_path}"
        self.timeout = options.timeout
        self.token = options.token
        self._client: ClientT | None = None

    async def _start(self) -> None:
        self._client = await self._connect()

    async def _close(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            await self._disconnect(client)

    def _require_client(self) -> ClientT:
        if self._client is None:
            raise RuntimeError("Client is not started")
        return self._client

    def _resolve_target(self, options: ClientOptions) -> str:
        if options.target is not None:
            return options.target
        advertised = os.environ.get(AXONX_SERVICE_TARGET)
        if advertised:
            try:
                return normalize_target(advertised)
            except ValueError:
                self.logger.warning(
                    f"Invalid {AXONX_SERVICE_TARGET} value: {advertised}"
                )
        return default_target()

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
