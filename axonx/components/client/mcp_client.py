"""MCP client for AxonX services."""

from contextlib import AsyncExitStack
from typing import TYPE_CHECKING, Any

from ...schema import JobInfo, Response
from ..component_registry import R
from .base_client import BaseClient

if TYPE_CHECKING:
    from fastmcp import Client


@R.register("mcp")
class McpClient(BaseClient["Client"]):
    """Call AxonX jobs through the Streamable HTTP MCP endpoint."""

    _url_path = "/mcp"
    _exit_stack: AsyncExitStack | None = None

    async def _start(self):
        from fastmcp import Client

        exit_stack = AsyncExitStack()
        self._exit_stack = exit_stack
        self.client = await exit_stack.enter_async_context(
            Client(self.url, timeout=self.timeout, auth=None),
        )

    async def _close(self):
        exit_stack = self._exit_stack
        if exit_stack is not None:
            await exit_stack.aclose()
            self.client = None
            self._exit_stack = None

    async def run_job(self, name: str, **kwargs: Any) -> Response:
        result = await self._require_client().call_tool(name, kwargs)
        return Response.model_validate(result.data)

    async def list_jobs(self) -> list[JobInfo]:
        tools = await self._require_client().list_tools()
        return [JobInfo.model_validate(tool.model_dump(by_alias=True)) for tool in tools]

    async def health(self) -> bool:
        client = self._require_client()
        try:
            return await client.ping()
        except Exception:  # noqa
            # A health probe represents every transport or protocol failure as False.
            return False
