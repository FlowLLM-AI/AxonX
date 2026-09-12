"""Demo step."""

from ...components import R
from .base_step import BaseStep


@R.register("demo_step")
class DemoStep(BaseStep):
    """Add a readable prefix to the version demo response."""

    async def execute(self):
        self.response.answer = f"Demo running on AxonX {self.response.answer}"
