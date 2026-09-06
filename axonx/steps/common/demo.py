"""A demo step that consumes the version step's output."""

from ..base_step import BaseStep
from ...components import R


@R.register("demo_step")
class DemoStep(BaseStep):
    """Show that sequential steps share one response."""

    async def execute(self):
        assert self.context is not None
        response = self.context.response
        response.answer = f"Demo running on AxonX {response.answer}"
        return response
