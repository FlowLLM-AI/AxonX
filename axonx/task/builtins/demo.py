"""Small built-in Task used to demonstrate synchronous execution."""

from ..core.base import BaseTask
from ..models.identity import TaskType
from ..models.params import BaseInputParams, BaseOutputParams


class DemoTaskInputParams(BaseInputParams):
    """Exercise validation, failure handling, and custom exit codes."""

    x: int
    y: int
    fail: bool = False


class DemoTaskOutputParams(BaseOutputParams):
    result: int
    branch: str
    operands: list[str]


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
    input_params: DemoTaskInputParams

    def build_task_steps(self):
        """Choose later steps from state populated by earlier steps."""
        yield self.initialize
        if self.state["branch"] == "equal":
            yield self.add_equal_operands
        else:
            yield self.add_x
            yield self.add_y
        if self.input_params.fail:
            yield self.fail
        yield self.finish

    def initialize(self) -> None:
        """Initialize shared state used by the lazy step generator."""
        self.report_progress(50)
        branch = "equal" if self.input_params.x == self.input_params.y else "different"
        self.state.update(total=0, operands=[], branch=branch)
        self.logger.info(f"Demo initialized x={self.input_params.x} y={self.input_params.y} branch={branch}")

    def add_equal_operands(self) -> None:
        """Use one conditional step when both operands are equal."""
        self._add_operands("x", "y")

    def add_x(self) -> None:
        """Add the first operand to the accumulator."""
        self._add_operands("x")

    def add_y(self) -> None:
        """Add the second operand to the accumulator."""
        self._add_operands("y")

    def _add_operands(self, *names: str) -> None:
        self.report_progress(50)
        self.state["operands"].extend(names)
        self.state["total"] += sum(getattr(self.input_params, name) for name in names)
        self.logger.info("Added operands={} total={}", names, self.state["total"])

    def fail(self) -> None:
        """Demonstrate framework-managed error status and exit code."""
        self.report_progress(50)
        self.logger.warning("Demo failure requested")
        raise RuntimeError("Demo failure requested")

    def finish(self) -> None:
        """Publish the accumulator as the task result."""
        self.report_progress(50)
        self.state["result"] = self.state["total"]
        self.logger.info(f"Demo result={self.state['result']} operands={self.state['operands']}")

    def build_output_params(self) -> DemoTaskOutputParams:
        return DemoTaskOutputParams(
            result=self.state["result"],
            branch=self.state["branch"],
            operands=self.state["operands"],
        )
