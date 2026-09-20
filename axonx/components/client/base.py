"""Transport-independent remote client lifecycle."""

import json
import os
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, PositiveFloat, model_validator

from ...constants import (
    AXONX_DEFAULT_CONNECT_HOST,
    AXONX_DEFAULT_PORT,
    AXONX_DEFAULT_REQUEST_TIMEOUT,
    AXONX_DEFAULT_SCHEME,
    AXONX_SERVICE_INFO,
    SERVICE_INFO_HOST_KEY,
    SERVICE_INFO_PORT_KEY,
)
from ...enums import ComponentEnum
from ..base import BaseComponent
from ..job.base import JobInfo, JobResponse


class ClientOptions(BaseModel):
    """Validated options for one remote AxonX connection."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    host_ip: str | None = Field(default=None, min_length=1)
    host_port: int | None = Field(default=None, ge=1, le=65535)
    timeout: PositiveFloat = AXONX_DEFAULT_REQUEST_TIMEOUT
    stream: bool = False
    token: str | None = Field(default=None, min_length=1, repr=False)
    stream_format: Literal["blocks", "json"] = "blocks"

    @model_validator(mode="after")
    def validate_address(self) -> Self:
        if (self.host_ip is None) != (self.host_port is None):
            raise ValueError("host_ip and host_port must be provided together")
        return self

    @classmethod
    def from_service_info(cls, service_info: str) -> Self:
        data = json.loads(service_info)
        if not isinstance(data, dict):
            raise ValueError("service info must be a JSON object")  # noqa: TRY004
        options = cls(
            host_ip=data.get(SERVICE_INFO_HOST_KEY),
            host_port=data.get(SERVICE_INFO_PORT_KEY),
        )
        if options.host_ip is None:
            raise ValueError("service info must declare both host and port")
        return options


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
        host_ip: str | None = None,
        host_port: int | None = None,
        timeout: float = AXONX_DEFAULT_REQUEST_TIMEOUT,
        token: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        options = ClientOptions(
            host_ip=host_ip, host_port=host_port, timeout=timeout, token=token
        )
        self.host_ip, self.host_port = self._resolve_address(options)
        url_host = f"[{self.host_ip}]" if ":" in self.host_ip else self.host_ip
        self.url = (
            f"{AXONX_DEFAULT_SCHEME}://{url_host}:{self.host_port}{self.url_path}"
        )
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

    def _resolve_address(self, options: ClientOptions) -> tuple[str, int]:
        if options.host_ip is not None and options.host_port is not None:
            return options.host_ip, options.host_port
        advertised = os.environ.get(AXONX_SERVICE_INFO)
        if advertised:
            try:
                discovered = ClientOptions.from_service_info(advertised)
            except ValueError:
                self.logger.warning(f"Invalid {AXONX_SERVICE_INFO} value: {advertised}")
            else:
                assert (
                    discovered.host_ip is not None and discovered.host_port is not None
                )
                return discovered.host_ip, discovered.host_port
        return AXONX_DEFAULT_CONNECT_HOST, AXONX_DEFAULT_PORT

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
        *,
        remote_ip: str | None = None,
    ) -> JobResponse:
        """Invoke one remote Job."""

    @abstractmethod
    async def list_jobs(self) -> list[JobInfo]:
        """List remotely exposed Jobs."""

    @abstractmethod
    async def health(self) -> bool:
        """Return whether the remote service is healthy."""
