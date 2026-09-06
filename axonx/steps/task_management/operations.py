"""Expose TaskManager operations through Application jobs."""

from ..base_step import BaseStep
from ...components import R
from ...enumeration import ComponentEnum


class TaskManagementStep(BaseStep):
    """Dispatch a common task manager operation selected by subclasses."""

    operation = "status"

    async def execute(self):
        manager = self.get_component(ComponentEnum.TASK_MANAGER, self.kwargs.get("manager", "default"))
        args = {**self.kwargs, **self.context}
        run_id = args.get("run_id")
        if self.operation == "status":
            result = await manager.status(run_id)
        elif self.operation == "wait":
            result = await manager.wait(run_id, args.get("timeout"))
        elif self.operation == "logs":
            result = await manager.logs(run_id, args.get("limit", 65536))
        else:
            result = await getattr(manager, self.operation)(run_id)
        self.context.response.answer = (
            [item.model_dump(mode="json") for item in result]
            if isinstance(result, list)
            else result.model_dump(mode="json") if hasattr(result, "model_dump") else result
        )


@R.register("submit_task")
class SubmitTask(BaseStep):
    """Submit a Task using ``task`` as identity and all other fields as config."""

    async def execute(self):
        arguments = {**self.kwargs, **self.context}
        manager_name = arguments.pop("manager", "default")
        try:
            task_name = arguments.pop("task")
        except KeyError:
            raise ValueError("Missing required Task argument: task") from None

        manager = self.get_component(ComponentEnum.TASK_MANAGER, manager_name)
        run_id = await manager.submit(task_name, arguments)
        self.context["run_id"] = run_id
        self.context.response.answer = {"run_id": run_id}


@R.register("task_status")
class TaskStatus(TaskManagementStep):
    """Return one task status or all known task statuses."""

    operation = "status"


@R.register("wait_task")
class WaitTask(TaskManagementStep):
    """Wait for a task run to reach a terminal state."""

    operation = "wait"


@R.register("cancel_task")
class CancelTask(TaskManagementStep):
    """Request cooperative task cancellation."""

    operation = "cancel"


@R.register("kill_task")
class KillTask(TaskManagementStep):
    """Force a task run to terminate."""

    operation = "kill"


@R.register("task_logs")
class TaskLogs(TaskManagementStep):
    """Read the trailing bytes of a task run log."""

    operation = "logs"


@R.register("report_task_progress")
class ReportTaskProgress(BaseStep):
    """Accept an internal worker progress update."""

    async def execute(self):
        arguments = {**self.kwargs, **self.context}
        manager = self.get_component(ComponentEnum.TASK_MANAGER, arguments.get("manager", "default"))
        record = await manager.report_progress(
            arguments["run_id"],
            arguments["step_index"],
            arguments["task_step"],
        )
        self.context.response.answer = {"run_id": record.id, "step_index": arguments["step_index"]}
