"""Abstract client interface shared by AxonX transports."""

import json
import os
from abc import ABC, abstractmethod
from typing import Any

from ...constants import (
    AXONX_DEFAULT_SCHEME,
    AXONX_DEFAULT_URL,
    AXONX_SERVICE_INFO,
)
from ...enumeration import ComponentEnum
from ...schema import JobInfo, Response
from ..base_component import BaseComponent


class BaseClient(BaseComponent, ABC):
    """Define discovery and job operations required from remote clients."""

    component_type = ComponentEnum.CLIENT

    def _discover_url(self) -> str:
        service_info = os.environ.get(AXONX_SERVICE_INFO)
        if not service_info:
            return AXONX_DEFAULT_URL
        try:
            data = json.loads(service_info)
            host, port = data["host"], data["port"]
            if not isinstance(host, str) or not host:
                raise ValueError("host has an invalid type")
            if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
                raise ValueError("port is invalid")
        except (KeyError, TypeError, ValueError):
            self.logger.warning(f"Invalid {AXONX_SERVICE_INFO} value: {service_info}")
            return AXONX_DEFAULT_URL
        return f"{AXONX_DEFAULT_SCHEME}://{host}:{port}"

    @abstractmethod
    async def run_job(self, name: str, **kwargs: Any) -> Response:
        """Invoke a named remote job with keyword arguments."""

    @abstractmethod
    async def list_jobs(self) -> list[JobInfo]:
        """List remotely callable jobs and their schemas."""
