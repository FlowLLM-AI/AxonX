"""Abstract client interface shared by AxonX transports."""

import json
import os
from abc import ABC, abstractmethod
from typing import Any

from ...constants import AXONX_DEFAULT_HOST, AXONX_DEFAULT_PORT, AXONX_SERVICE_INFO
from ...enumeration import ComponentEnum
from ...schema import HttpClientOptions, JobInfo, Response
from ..base_component import BaseComponent


class BaseClient(BaseComponent, ABC):
    """Define discovery and job operations required from remote clients."""

    component_type = ComponentEnum.CLIENT

    def _resolve_address(self, options: HttpClientOptions) -> tuple[str, int]:
        address = options.host_ip, options.host_port
        if options.host_ip is None or options.host_port is None or address == (AXONX_DEFAULT_HOST, AXONX_DEFAULT_PORT):
            return self._discover_address()
        return options.host_ip, options.host_port

    def _discover_address(self) -> tuple[str, int]:
        service_info = os.environ.get(AXONX_SERVICE_INFO)
        if not service_info:
            return AXONX_DEFAULT_HOST, AXONX_DEFAULT_PORT
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
            return AXONX_DEFAULT_HOST, AXONX_DEFAULT_PORT


    @abstractmethod
    async def run_job(self, name: str, **kwargs: Any) -> Response:
        """Invoke a named remote job with keyword arguments."""

    @abstractmethod
    async def list_jobs(self) -> list[JobInfo]:
        """List remotely callable jobs and their schemas."""

    @abstractmethod
    async def health(self) -> bool:
        """Return whether the remote service is healthy."""
