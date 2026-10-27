"""Local hardware and runtime diagnostics, with configured remote machine health checks."""

import asyncio
import os
import platform
import shutil
import sys
from pathlib import Path

import psutil

from ....client import http as client
from ...config.models import TargetConfig
from .build_info import get_build_info
from .gpu import collect_gpus
from .models import CpuInfo, MachineDiagnostics, MachineHealth, MachineInfo, MemoryInfo


def collect_machine_info(sample_interval: float, logger) -> MachineInfo:
    build = get_build_info()
    gpu_collection = collect_gpus()
    for warning in gpu_collection.warnings:
        logger.warning(warning)
    return MachineInfo(
        axonx=build,
        cpu=collect_cpu(sample_interval),
        memory=collect_memory(),
        gpus=list(gpu_collection.devices),
    )


def collect_cpu(sample_interval: float) -> CpuInfo:
    return CpuInfo(
        total_cores=psutil.cpu_count(logical=True),
        physical_cores=psutil.cpu_count(logical=False),
        usage_percent=psutil.cpu_percent(interval=sample_interval),
    )


def collect_memory() -> MemoryInfo:
    memory = psutil.virtual_memory()
    return MemoryInfo(
        total_bytes=memory.total,
        used_bytes=memory.used,
        available_bytes=memory.available,
        usage_percent=memory.percent,
    )


CREDENTIAL_NAMES = ("AXONX_SERVICE_TOKEN", "AXONX_TARGET_TOKEN", "AXONX_TUSHARE_TOKEN")


def collect_diagnostics(workspace: Path, logger, *, service_auth_enabled: bool = False) -> MachineDiagnostics:
    """Inspect installed state and the workspace filesystem without creating files."""
    workspace = workspace.resolve()
    disk_path = workspace
    while not disk_path.exists() and disk_path != disk_path.parent:
        disk_path = disk_path.parent
    disk = shutil.disk_usage(disk_path)
    return MachineDiagnostics.model_validate(
        {
            **collect_machine_info(0.1, logger).model_dump(mode="json"),
            "python": {
                "version": platform.python_version(),
                "executable": sys.executable,
            },
            "platform": platform.system(),
            "cwd": str(Path.cwd()),
            "workspace": {
                "path": str(workspace),
                "exists": workspace.exists(),
                "disk": {
                    "path": str(disk_path),
                    "total_bytes": disk.total,
                    "used_bytes": disk.used,
                    "free_bytes": disk.free,
                },
            },
            "credentials_configured": {name: bool(os.environ.get(name)) for name in CREDENTIAL_NAMES},
            "service_auth_enabled": service_auth_enabled,
        }
    )


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
