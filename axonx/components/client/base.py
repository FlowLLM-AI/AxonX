"""Abstract client interface shared by AxonX transports."""

import json
import os
from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from ...constants import (
    AXONX_DEFAULT_CONNECT_HOST,
    AXONX_DEFAULT_PORT,
    AXONX_DEFAULT_REQUEST_TIMEOUT,
    AXONX_DEFAULT_SCHEME,
    AXONX_SERVICE_INFO,
)
from ...enums import ComponentEnum
from ...schema import ClientOptions, JobInfo, Response
from ..base import BaseComponent

ClientT = TypeVar("ClientT")


class BaseClient(BaseComponent, ABC, Generic[ClientT]):
    """Define discovery and job operations required from remote clients."""

    component_type = ComponentEnum.CLIENT
    _url_path = ""

    def __init__(
        self,
        host_ip: str | None = None,
        host_port: int | None = None,
        timeout: float = AXONX_DEFAULT_REQUEST_TIMEOUT,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        options = ClientOptions(host_ip=host_ip, host_port=host_port, timeout=timeout)
        self.host_ip, self.host_port = self._resolve_address(options)
        url_host = f"[{self.host_ip}]" if ":" in self.host_ip else self.host_ip
        self.url = f"{AXONX_DEFAULT_SCHEME}://{url_host}:{self.host_port}{self._url_path}"
        self.timeout = options.timeout
        self.client: ClientT | None = None

    def _require_client(self) -> ClientT:
        """Return the active transport client or fail with a clear lifecycle error."""
        if self.client is None:
            raise RuntimeError("Client is not started")
        return self.client

    def _resolve_address(self, options: ClientOptions) -> tuple[str, int]:
        if options.host_ip is None or options.host_port is None:
            return self._discover_address()
        return options.host_ip, options.host_port

    def _discover_address(self) -> tuple[str, int]:
        service_info = os.environ.get(AXONX_SERVICE_INFO)
        if not service_info:
            return AXONX_DEFAULT_CONNECT_HOST, AXONX_DEFAULT_PORT
        try:
            data = json.loads(service_info)
            host, port = data["host"], data["port"]
            if not isinstance(host, str) or not host:
                raise ValueError("host has an invalid type")
            if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
                raise ValueError("port is invalid")
            return host, port
        except (KeyError, TypeError, ValueError):
            self.logger.warning(f"Invalid {AXONX_SERVICE_INFO} value: {service_info}")
            return AXONX_DEFAULT_CONNECT_HOST, AXONX_DEFAULT_PORT

    @abstractmethod
    async def run_job(self, name: str, **kwargs: Any) -> Response:
        """Invoke a named remote job with keyword arguments."""

    @abstractmethod
    async def list_jobs(self) -> list[JobInfo]:
        """List remotely callable jobs and their schemas."""

    @abstractmethod
    async def health(self) -> bool:
        """Return whether the remote service is healthy."""
