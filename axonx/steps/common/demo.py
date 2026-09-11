"""A demo step that consumes the version step's output."""

from ..base_step import BaseStep
from ...components import R


@R.register("demo_step")
class DemoStep(BaseStep):
    """Show that sequential steps share one response."""

    async def execute(self):
        self.response.answer = f"Demo running on AxonX {self.response.answer}"
