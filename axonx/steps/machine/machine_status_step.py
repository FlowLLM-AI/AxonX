"""Local-machine status step."""

from ...components import R
from ..common.base_step import BaseStep


@R.register("machine_status_step")
class MachineStatusStep(BaseStep):
    """Collect status from the local machine component."""

    async def execute(self):
        self.response.answer = await self.machine.get_info()
