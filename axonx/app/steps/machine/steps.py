"""Thin Job adapters for machine operations."""

import asyncio

from ..base import BaseStep
from .diagnostics import collect_diagnostics
from .health import check_machines
from .metrics import collect_machine_info
from .python import run_python
from ....common.registry import provider

CPU_SAMPLE_INTERVAL_SECONDS = 0.1


@provider("diagnose_step")
class DiagnoseStep(BaseStep):
    async def execute(self):
        self.response.answer = await asyncio.to_thread(
            collect_diagnostics,
            self.workspace_path,
            self.logger,
            service_auth_enabled=bool(getattr(self.app_context.service, "token", None)),
        )


@provider("machine_status")
class MachineStatusStep(BaseStep):
    def __init__(self, cpu_sample_interval: float = CPU_SAMPLE_INTERVAL_SECONDS, **kwargs) -> None:
        super().__init__(**kwargs)
        if isinstance(cpu_sample_interval, bool) or not isinstance(cpu_sample_interval, (int, float)):
            raise TypeError("cpu_sample_interval must be a number")
        if cpu_sample_interval < 0:
            raise ValueError("cpu_sample_interval must be non-negative")
        self.cpu_sample_interval = float(cpu_sample_interval)

    async def execute(self):
        self.response.answer = await asyncio.to_thread(collect_machine_info, self.cpu_sample_interval, self.logger)


@provider("machine_list")
class ListMachinesStep(BaseStep):
    async def execute(self):
        self.response.answer = await check_machines(self.app_config.targets, self.logger)


@provider("machine_python")
class PythonStep(BaseStep):
    async def execute(self):
        success, output = await run_python(self.context["code"], self.context.get("timeout", 30))
        self.response.success = success
        self.response.answer = output
