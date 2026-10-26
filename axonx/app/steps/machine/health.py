"""Check configured remote machine health independently."""

import asyncio

from ....client import http as client
from ...config.models import TargetConfig
from .models import MachineHealth

HEALTH_TIMEOUT_SECONDS = 5.0


async def check_machines(targets: list[TargetConfig], logger) -> list[MachineHealth]:
    return list(await asyncio.gather(*(_check_machine(target, logger) for target in targets)))


async def _check_machine(target: TargetConfig, logger) -> MachineHealth:
    try:
        async with client.HttpClient(
            target=target.address,
            timeout=HEALTH_TIMEOUT_SECONDS,
            token=target.token,
        ) as remote:
            healthy = await remote.health()
    except Exception as exc:
        logger.warning(f"Machine health check failed for {target.address}: {exc}")
        healthy = False
    return MachineHealth(address=target.address, healthy=healthy)
