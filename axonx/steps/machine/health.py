"""Check configured remote machine health independently."""

import asyncio

from ...components.client import HttpClient
from ...config import RemoteNode
from .contracts import MachineHealth

HEALTH_TIMEOUT_SECONDS = 5.0


async def check_machines(nodes: list[RemoteNode], logger) -> list[MachineHealth]:
    return list(await asyncio.gather(*(_check_machine(node, logger) for node in nodes)))


async def _check_machine(node: RemoteNode, logger) -> MachineHealth:
    try:
        async with HttpClient(
            host_ip=node.host_ip,
            host_port=node.host_port,
            timeout=HEALTH_TIMEOUT_SECONDS,
            token=node.token,
        ) as client:
            healthy = await client.health()
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning(f"Machine health check failed for {node.address}: {exc}")
        healthy = False
    return MachineHealth(address=node.address, healthy=healthy)
