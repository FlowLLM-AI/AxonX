"""Small built-in task used to demonstrate synchronous task execution."""

from ..base_task import BaseConfig, BaseTask
from ...components.component_registry import R
from ...enumeration import TaskType


class DemoTaskConfig(BaseConfig):
    """Exercise validation, failure handling, and custom exit codes."""

    x: int
    y: int
    fail: bool = False


@R.register("demo")
class DemoTask(BaseTask):
    """Demonstrate the complete synchronous Task contract."""

    config_cls = DemoTaskConfig
    task_type = TaskType.ANALYSIS
    output_keys = ("result", "branch", "operands")

    def build_task_steps(self):
        """Choose later steps from context populated by earlier steps."""
        yield self.initialize
        if self.context["branch"] == "equal":
            yield self.add_equal_operands
        else:
            yield self.add_x
            yield self.add_y
        if self.config.fail:
            yield self.fail
        yield self.finish

    def initialize(self) -> None:
        """Initialize shared context used by the lazy step generator."""
        self.report_progress(50)
        branch = "equal" if self.config.x == self.config.y else "different"
        self.context.update(total=0, operands=[], branch=branch)

    def add_equal_operands(self) -> None:
        """Use one conditional step when both operands are equal."""
        self.report_progress(50)
        self.context["operands"].extend(("x", "y"))
        self.context["total"] += self.config.x + self.config.y

    def add_x(self) -> None:
        """Add the first operand to the accumulator."""
        self.report_progress(50)
        self.context["operands"].append("x")
        self.context["total"] += self.config.x

    def add_y(self) -> None:
        """Add the second operand to the accumulator."""
        self.report_progress(50)
        self.context["operands"].append("y")
        self.context["total"] += self.config.y

    def fail(self) -> None:
        """Demonstrate framework-managed error status and exit code."""
        self.report_progress(50)
        raise RuntimeError("Demo failure requested")

    def finish(self) -> None:
        """Publish the accumulator as the task result."""
        self.report_progress(50)
        self.context["result"] = self.context["total"]

    def exit_code(self, _output) -> int:
        """Demonstrate a Task-defined process exit code."""
        return 0
