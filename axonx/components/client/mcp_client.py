"""MCP client for AxonX services."""

from contextlib import AsyncExitStack

from typing import Any

from ...constants import AXONX_DEFAULT_REQUEST_TIMEOUT, AXONX_DEFAULT_SCHEME
from ...schema import HttpClientOptions, JobInfo, Response
from .base_client import BaseClient
from ..component_registry import R


@R.register("mcp")
class McpClient(BaseClient):
    """Call AxonX jobs through the Streamable HTTP MCP endpoint."""

    def __init__(self, host_ip=None, host_port=None, timeout=AXONX_DEFAULT_REQUEST_TIMEOUT, **kwargs):
        super().__init__(**kwargs)
        options = HttpClientOptions(host_ip=host_ip, host_port=host_port, timeout=timeout)
        self.host_ip, self.host_port = self._resolve_address(options)
        base_url = f"{AXONX_DEFAULT_SCHEME}://{self.host_ip}:{self.host_port}"
        self.url = f"{base_url}/mcp"
        self.timeout = options.timeout
        self.client = None
        self._exit_stack = None

    async def _start(self):
        from fastmcp import Client

        self._exit_stack = AsyncExitStack()
        self.client = await self._exit_stack.enter_async_context(Client(self.url, timeout=self.timeout, auth=None))

    async def _close(self):
        if self.client is not None:
            await self._exit_stack.aclose()
            self.client = None
            self._exit_stack = None

    def _require_client(self):
        if self.client is None:
            raise RuntimeError("Client is not started")
        return self.client

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
        except Exception:
            return False
