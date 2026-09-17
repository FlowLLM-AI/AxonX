"""Small built-in task used to demonstrate synchronous task execution."""

from ...components.registry import R
from ...enums import TaskType
from ..base import BaseInputParams, BaseOutputParams, BaseTask


class DemoTaskInputParams(BaseInputParams):
    """Exercise validation, failure handling, and custom exit codes."""

    x: int
    y: int
    fail: bool = False


class DemoTaskOutputParams(BaseOutputParams):
    result: int
    branch: str
    operands: list[str]


@R.register("demo")
class DemoTask(BaseTask):
    """Demonstrate synchronous Task execution with a small arithmetic workflow.

    The Task selects a conditional step sequence from its validated operands,
    reports progress, and publishes both the sum and the branch that produced
    it. Its optional failure mode exercises framework-managed error status and
    exit-code handling without reading or writing external data.
    """

    task_type = TaskType.BASE
    input_cls = DemoTaskInputParams
    output_cls = DemoTaskOutputParams

    def build_task_steps(self):
        """Choose later steps from context populated by earlier steps."""
        yield self.initialize
        if self.context["branch"] == "equal":
            yield self.add_equal_operands
        else:
            yield self.add_x
            yield self.add_y
        if self.input_params.fail:
            yield self.fail
        yield self.finish

    def initialize(self) -> None:
        """Initialize shared context used by the lazy step generator."""
        self.report_progress(50)
        branch = "equal" if self.input_params.x == self.input_params.y else "different"
        self.context.update(total=0, operands=[], branch=branch)
        self.logger.info(f"Demo initialized x={self.input_params.x} y={self.input_params.y} branch={branch}")

    def add_equal_operands(self) -> None:
        """Use one conditional step when both operands are equal."""
        self.report_progress(50)
        self.context["operands"].extend(("x", "y"))
        self.context["total"] += self.input_params.x + self.input_params.y
        self.logger.info(f"Added equal operands total={self.context['total']}")

    def add_x(self) -> None:
        """Add the first operand to the accumulator."""
        self.report_progress(50)
        self.context["operands"].append("x")
        self.context["total"] += self.input_params.x
        self.logger.info(f"Added operand x total={self.context['total']}")

    def add_y(self) -> None:
        """Add the second operand to the accumulator."""
        self.report_progress(50)
        self.context["operands"].append("y")
        self.context["total"] += self.input_params.y
        self.logger.info(f"Added operand y total={self.context['total']}")

    def fail(self) -> None:
        """Demonstrate framework-managed error status and exit code."""
        self.report_progress(50)
        self.logger.warning("Demo failure requested")
        raise RuntimeError("Demo failure requested")

    def finish(self) -> None:
        """Publish the accumulator as the task result."""
        self.report_progress(50)
        self.context["result"] = self.context["total"]
        self.logger.info(f"Demo result={self.context['result']} operands={self.context['operands']}")

    def build_output_params(self) -> DemoTaskOutputParams:
        return DemoTaskOutputParams(
            result=self.context["result"],
            branch=self.context["branch"],
            operands=self.context["operands"],
        )
