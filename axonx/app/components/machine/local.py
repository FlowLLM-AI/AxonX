"""Local machine component: resource sampling, diagnostics and target health checks."""

import asyncio
import math
import os
import platform
import shutil
import sys
from pathlib import Path

import psutil

from ....client import http as client
from ....utils.async_work import run_blocking
from ...config.models import TargetConfig
from ..registry import provider
from .base import BaseMachineComponent
from .build_info import get_build_info
from .gpu import collect_gpus
from .models import CpuInfo, MachineDiagnostics, MachineHealth, MachineInfo, MemoryInfo, PythonOutput
from .python import run_python

CREDENTIAL_NAMES = ("AXONX_SERVICE_TOKEN", "AXONX_TARGET_TOKEN", "AXONX_TUSHARE_TOKEN")
HEALTH_TIMEOUT_SECONDS = 5.0


@provider("local")
class LocalMachineComponent(BaseMachineComponent):
    """Own local machine operations using the application's workspace and targets."""

    def __init__(self, cpu_sample_interval: float = 0.1, **kwargs) -> None:
        super().__init__(**kwargs)
        if isinstance(cpu_sample_interval, bool) or not isinstance(cpu_sample_interval, (int, float)):
            raise TypeError("cpu_sample_interval must be a number")
        if not math.isfinite(cpu_sample_interval) or cpu_sample_interval < 0:
            raise ValueError("cpu_sample_interval must be finite and non-negative")
        self.cpu_sample_interval = float(cpu_sample_interval)

    async def status(self) -> MachineInfo:
        return await run_blocking(self._collect_info)

    async def diagnose(self) -> MachineDiagnostics:
        return await run_blocking(self._collect_diagnostics)

    async def list_machines(self) -> list[MachineHealth]:
        async with asyncio.TaskGroup() as group:
            checks = [group.create_task(self._check_machine(target)) for target in self.app_config.targets]
        return [check.result() for check in checks]

    async def run_python(self, code: str, timeout: float = 30) -> PythonOutput:
        return await run_python(code, timeout)

    def _collect_info(self) -> MachineInfo:
        memory = psutil.virtual_memory()
        return MachineInfo(
            axonx=get_build_info(),
            cpu=CpuInfo(
                total_cores=psutil.cpu_count(logical=True),
                physical_cores=psutil.cpu_count(logical=False),
                usage_percent=psutil.cpu_percent(interval=self.cpu_sample_interval),
            ),
            memory=MemoryInfo(
                total_bytes=memory.total,
                used_bytes=memory.used,
                available_bytes=memory.available,
                usage_percent=memory.percent,
            ),
            gpus=collect_gpus(self.logger.warning),
        )

    def _collect_diagnostics(self) -> MachineDiagnostics:
        workspace = self.workspace_path.resolve()
        disk_path = workspace
        while not disk_path.exists() and disk_path != disk_path.parent:
            disk_path = disk_path.parent
        disk = shutil.disk_usage(disk_path)
        return MachineDiagnostics(
            **dict(self._collect_info()),
            python={"version": platform.python_version(), "executable": sys.executable},
            platform=platform.system(),
            cwd=str(Path.cwd()),
            workspace={
                "path": str(workspace),
                "exists": workspace.exists(),
                "disk": {
                    "path": str(disk_path),
                    "total_bytes": disk.total,
                    "used_bytes": disk.used,
                    "free_bytes": disk.free,
                },
            },
            credentials_configured={name: bool(os.environ.get(name)) for name in CREDENTIAL_NAMES},
            service_auth_enabled=bool(getattr(self._require_context().service, "token", None)),
        )

    async def _check_machine(self, target: TargetConfig) -> MachineHealth:
        try:
            async with client.HttpClient(
                target=target.address,
                timeout=HEALTH_TIMEOUT_SECONDS,
                token=target.token,
            ) as remote:
                healthy = await remote.health()
        except Exception as exc:
            self.logger.warning(f"Machine health check failed for {target.address}: {exc}")
            healthy = False
        return MachineHealth(address=target.address, healthy=healthy)
