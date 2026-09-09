"""HTTP client for AxonX REST services."""

from typing import Any
from urllib.parse import quote

import httpx

from ...constants import AXONX_DEFAULT_REQUEST_TIMEOUT
from ...schema import HttpClientOptions, JobInfo, Response
from .base_client import BaseClient
from ..component_registry import R


@R.register("http")
class HttpClient(BaseClient):
    """Call AxonX jobs through its JSON REST endpoints."""

    def __init__(self, url=None, timeout=AXONX_DEFAULT_REQUEST_TIMEOUT, **kwargs):
        super().__init__(**kwargs)
        options = HttpClientOptions(url=url, timeout=timeout)
        self.url = options.url or self._discover_url()
        self.timeout = options.timeout
        self.client = None

    async def _start(self):
        self.client = httpx.AsyncClient(base_url=self.url, timeout=self.timeout)

    async def _close(self):
        if self.client is not None:
            await self.client.aclose()
            self.client = None

    def _require_client(self):
        if self.client is None:
            raise RuntimeError("Client is not started")
        return self.client

    async def run_job(self, name: str, **kwargs: Any) -> Response:
        response = await self._require_client().post(
            f"/jobs/{quote(name, safe='')}",
            json=kwargs,
        )
        response.raise_for_status()
        return Response.model_validate_json(response.content)

    async def list_jobs(self) -> list[JobInfo]:
        response = await self._require_client().get("/jobs")
        response.raise_for_status()
        return [JobInfo.model_validate(item) for item in response.json()]

    async def health(self) -> bool:
        """Return whether the remote AxonX service is running."""
        try:
            response = await self._require_client().get("/health")
            response.raise_for_status()
            data = response.json()
            return isinstance(data, dict) and data.get("running") is True
        except (httpx.HTTPError, ValueError):
            return False
