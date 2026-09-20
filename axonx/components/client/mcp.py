"""MCP client for the ordinary AxonX Job response surface."""

from contextlib import AsyncExitStack
from typing import Any

from pydantic import ValidationError

from ...constants import PROTOCOL_ROUTE_MCP
from ..job.base import JobInfo, JobResponse
from .base import BaseClient, RemoteServiceError


class McpClient(BaseClient[Any]):
    """Call ordinary AxonX Jobs through Streamable HTTP MCP."""

    url_path = PROTOCOL_ROUTE_MCP

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._exit_stack: AsyncExitStack | None = None

    async def _connect(self) -> Any:
        from fastmcp import Client as FastMCPClient
        from fastmcp.client.auth import BearerAuth

        stack = AsyncExitStack()
        auth = BearerAuth(self.token) if self.token else None
        try:
            client = await stack.enter_async_context(
                FastMCPClient(self.url, timeout=self.timeout, auth=auth)
            )
        except Exception as exc:
            await stack.aclose()
            raise RemoteServiceError(f"Remote MCP connection failed: {exc}") from exc
        except BaseException:
            await stack.aclose()
            raise
        self._exit_stack = stack
        return client

    async def _disconnect(self, _client: Any) -> None:
        stack, self._exit_stack = self._exit_stack, None
        if stack is not None:
            await stack.aclose()

    async def run_job(self, name: str, arguments=None, *, remote_ip: str | None = None) -> JobResponse:
        if remote_ip is not None:
            raise ValueError("MCP client does not support relayed remote execution")
        try:
            result = await self._require_client().call_tool(name, dict(arguments or {}))
            payload = (
                result.structured_content
                if result.structured_content is not None
                else result.data
            )
            return JobResponse.model_validate(payload)
        except ValidationError as exc:
            raise RemoteServiceError(
                "Remote MCP service returned an invalid response envelope"
            ) from exc
        except Exception as exc:
            raise RemoteServiceError(f"Remote MCP request failed: {exc}") from exc

    async def list_jobs(self) -> list[JobInfo]:
        try:
            tools = await self._require_client().list_tools()
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
            raise RemoteServiceError(
                "Remote MCP service returned an invalid job catalog"
            ) from exc
        except Exception as exc:
            raise RemoteServiceError(f"Remote MCP request failed: {exc}") from exc

    async def health(self) -> bool:
        try:
            return bool(await self._require_client().ping())
        except Exception:  # noqa: BLE001 - health folds transport failures into False.
            return False
