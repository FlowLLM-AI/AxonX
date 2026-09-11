"""Discover configured remote AxonX services."""

import asyncio

from ...components import R
from ...components.client import HttpClient
from ..base_step import BaseStep


@R.register("list_machines_step")
class ListMachinesStep(BaseStep):
    """Check the health of every remote AxonX in the application config."""

    async def execute(self):
        assert self.context is not None
        addresses = self.app_config.remote_nodes
        self.context.response.answer = await asyncio.gather(*(self._check(address) for address in addresses))
        return self.context.response

    @staticmethod
    async def _check(address: str) -> dict:
        host_ip, host_port = address.rsplit(":", 1)
        async with HttpClient(host_ip=host_ip, host_port=int(host_port), timeout=5) as client:
            healthy = await client.health()
        return {"address": address, "healthy": healthy}
