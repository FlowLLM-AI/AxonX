"""Thin Job adapters for machine operations."""

from abc import ABC

from ..components.machine.base import BaseMachineComponent
from ..components.registry import provider
from .base import BaseStep


class MachineStep(BaseStep, ABC):
    """Resolve the configured machine component for one Job invocation."""

    @property
    def machine(self) -> BaseMachineComponent:
        return self.component(BaseMachineComponent)


@provider("diagnose_step")
class DiagnoseStep(MachineStep):
    async def execute(self):
        self.response.answer = await self.machine.diagnose()


@provider("machine_status")
class MachineStatusStep(MachineStep):
    async def execute(self):
        self.response.answer = await self.machine.status()


@provider("machine_list")
class ListMachinesStep(MachineStep):
    async def execute(self):
        self.response.answer = await self.machine.list_machines()


@provider("machine_python")
class PythonStep(MachineStep):
    async def execute(self):
        output = await self.machine.run_python(self.context["code"], self.context.get("timeout", 30))
        self.response.success = output.exit_code == 0
        self.response.answer = output
