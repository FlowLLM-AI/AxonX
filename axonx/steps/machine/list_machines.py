"""Remote-machine discovery step."""

import asyncio

from ...components.registry import R
from ...components.client import HttpClient
from ...schema import RemoteNode
from ..base import BaseStep


@R.register("list_machines_step")
class ListMachinesStep(BaseStep):
    """Check the health of every configured remote node."""

    async def execute(self):
        self.response.answer = await asyncio.gather(
            *(self._check(node) for node in self.app_config.remote_nodes),
        )

    @staticmethod
    async def _check(node: RemoteNode) -> dict:
        async with HttpClient(
            host_ip=node.host_ip, host_port=node.host_port, timeout=5
        ) as client:
            return {"address": node.address, "healthy": await client.health()}
