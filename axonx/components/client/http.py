"""HTTP client for AxonX REST services."""

import hashlib
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from ...schema import JobInfo, Response, TaskStatus
from ..registry import R
from .base import BaseClient


@R.register("http")
class HttpClient(BaseClient[httpx.AsyncClient]):
    """Call AxonX jobs through its JSON REST endpoints."""

    client: httpx.AsyncClient | None

    async def _start(self):
        """Create the underlying asynchronous HTTP client."""
        self.client = httpx.AsyncClient(base_url=self.url, timeout=self.timeout)

    async def _close(self):
        """Close and release the underlying asynchronous HTTP client."""
        client = self.client
        if client is not None:
            await client.aclose()
            self.client = None

    async def run_job(self, name: str, **kwargs: Any) -> Response:
        """Invoke a named remote job with JSON arguments."""
        response = await self._require_client().post(f"/jobs/{quote(name, safe='')}", json=kwargs)
        response.raise_for_status()
        return Response.model_validate_json(response.content)

    async def set_status(self, status: TaskStatus) -> Response:
        """Report one complete Task status snapshot."""
        return await self.run_job(
            "set_status",
            task_id=status.task_id,
            status=status.model_dump(mode="json"),
        )

    async def list_jobs(self) -> list[JobInfo]:
        """Return the jobs exposed by the remote service."""
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

    async def install_plugin(self, wheel: Path, token: str | None = None) -> dict:
        """Upload and install one wheel on a remote AxonX service."""
        data = wheel.read_bytes()
        headers = {
            "content-type": "application/octet-stream",
            "x-wheel-filename": wheel.name,
            "x-wheel-sha256": hashlib.sha256(data).hexdigest(),
        }
        if token:
            headers["authorization"] = f"Bearer {token}"
        response = await self._require_client().post("/plugins", content=data, headers=headers)
        response.raise_for_status()
        return response.json()
