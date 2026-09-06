"""Small built-in task used to demonstrate synchronous task execution."""

from ...components.component_registry import R
from ..base_task import BaseConfig, BaseTask


class DemoTaskConfig(BaseConfig):
    """Configure the two operands accepted by :class:`DemoTask`."""

    x: int
    y: int


@R.register("demo")
class DemoTask(BaseTask):
    """Add two integers through lazily generated task steps."""

    config: DemoTaskConfig
    output_keys = ("result",)

    def build_task_steps(self):
        """Yield the demonstration's initialization and addition steps."""
        yield self.initialize
        yield self.record_branch
        yield self.add_x
        yield self.add_y
        yield self.finish

    def initialize(self) -> None:
        """Initialize the shared accumulator and diagnostic values."""
        self.context.update(total=0, operands=[], branch="")

    def record_branch(self) -> None:
        """Record whether the two configured operands are equal."""
        self.context["branch"] = "equal" if self.config.x == self.config.y else "different"

    def add_x(self) -> None:
        """Add the first operand to the accumulator."""
        self.context["operands"].append("x")
        self.context["total"] += self.config.x

    def add_y(self) -> None:
        """Add the second operand to the accumulator."""
        self.context["operands"].append("y")
        self.context["total"] += self.config.y

    def finish(self) -> None:
        """Publish the accumulator as the task result."""
        self.context["result"] = self.context["total"]
