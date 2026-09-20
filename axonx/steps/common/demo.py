"""Demo step."""

from ...components.registry import provider
from ..base import BaseStep


@provider("demo_step")
class DemoStep(BaseStep):
    """Add a readable prefix to the version demo response."""

    async def execute(self):
        self.response.answer = f"Demo running on AxonX {self.response.answer}"
