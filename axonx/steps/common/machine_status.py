"""Expose local and remote machine discovery through standard jobs."""

from ...components import R
from ..base_step import BaseStep


@R.register("machine_status_step")
class MachineStatusStep(BaseStep):
    """Collect local status, or remote status when an address is supplied."""

    async def execute(self):
        assert self.context is not None
        self.context.response.answer = await self.machine.get_info(
            self.context.get("address"),
        )
        return self.context.response
