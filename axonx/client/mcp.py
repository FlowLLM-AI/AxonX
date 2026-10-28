"""MCP client for the ordinary AxonX Job response surface."""

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from .base import BaseClient, RemoteServiceError
from .config import PROTOCOL_ROUTE_MCP
from .models import JobInfo, JobResponse

if TYPE_CHECKING:
    from fastmcp import Client as FastMCPClient


class McpClient(BaseClient["FastMCPClient"]):
    """Call ordinary AxonX Jobs through Streamable HTTP MCP."""

    async def _connect(self) -> "FastMCPClient":
        from fastmcp import Client as FastMCPClient
        from fastmcp.client.auth import BearerAuth

        auth = BearerAuth(self.token) if self.token else None
        client = FastMCPClient(f"{self.target}{PROTOCOL_ROUTE_MCP}", timeout=self.timeout, auth=auth)
        try:
            # The SDK context spans our separate start/close calls.
            return await client.__aenter__()  # pylint: disable=unnecessary-dunder-call
        except Exception as exc:
            raise RemoteServiceError(f"Remote MCP connection failed: {exc}") from exc

    async def _disconnect(self, client: "FastMCPClient") -> None:
        await client.__aexit__(None, None, None)

    async def run_job(self, name: str, arguments: Mapping[str, Any] | None = None) -> JobResponse:
        client = self._require_client()
        try:
            result = await client.call_tool(name, dict(arguments or {}))
        except Exception as exc:
            raise RemoteServiceError(f"Remote MCP request failed: {exc}") from exc
        return self._parse_payload(result.structured_content, JobResponse)

    async def list_jobs(self) -> list[JobInfo]:
        client = self._require_client()
        try:
            tools = await client.list_tools()
        except Exception as exc:
            raise RemoteServiceError(f"Remote MCP request failed: {exc}") from exc
        try:
            return [
                JobInfo(
                    name=tool.name,
                    description=tool.description or "",
                    input_schema=tool.input_schema,
                    output_schema=tool.output_schema or {},
                )
                for tool in tools
            ]
        except ValidationError as exc:
            raise RemoteServiceError("Remote MCP service returned an invalid job catalog") from exc

    async def health(self) -> bool:
        client = self._require_client()
        try:
            await client.list_tools()
            return True
        except Exception:  # noqa: BLE001 - health folds transport failures into False.
            return False
