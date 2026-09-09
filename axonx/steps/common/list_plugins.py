"""Expose installed Task plugins through a standard job."""

from ...components import R
from ...enumeration import ComponentEnum
from ..base_step import BaseStep


@R.register("list_plugins_step")
class ListPluginsStep(BaseStep):
    """List plugins known to the local plugin component."""

    async def execute(self):
        assert self.context is not None
        self.context.response.answer = self.get_component(ComponentEnum.PLUGIN).status()
