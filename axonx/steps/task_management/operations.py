"""Expose TaskManager operations through Application jobs."""

from ..base_step import BaseStep
from ...components import R
from ...enumeration import ComponentEnum
from ...utils.cli_utils import pop_required_string


def _answer(value):
    return value.model_dump(mode="json") if hasattr(value, "model_dump") else value


class TaskManagementStep(BaseStep):
    """Resolve the selected task manager."""

    def manager_and_arguments(self):
        arguments = {**self.kwargs, **self.context}
        manager = self.get_component(
            ComponentEnum.TASK_MANAGER,
            arguments.pop("manager", "default"),
        )
        return manager, arguments


@R.register("submit_task")
class SubmitTask(TaskManagementStep):
    """Submit a Task using all remaining fields as its config."""

    async def execute(self):
        manager, arguments = self.manager_and_arguments()
        task, arguments = pop_required_string(arguments, "task")
        suffix = arguments.pop("suffix", None)
        task_id = await manager.submit(task, arguments, suffix=suffix)
        self.context["task_id"] = task_id
        self.context.response.answer = {"task_id": task_id}


@R.register("list_tasks")
class ListTasks(TaskManagementStep):
    """List all known task identifiers."""

    async def execute(self):
        manager, _ = self.manager_and_arguments()
        self.context.response.answer = await manager.list_task_ids()


@R.register("get_task_status")
class GetTaskStatus(TaskManagementStep):
    """Return one task status."""

    async def execute(self):
        manager, arguments = self.manager_and_arguments()
        self.context.response.answer = _answer(await manager.get_status(arguments["task_id"]))


@R.register("wait_task")
class WaitTask(TaskManagementStep):
    """Wait for one task to finish."""

    async def execute(self):
        manager, arguments = self.manager_and_arguments()
        result = await manager.wait(arguments["task_id"], arguments.get("timeout"))
        self.context.response.answer = _answer(result)


@R.register("cancel_task")
class CancelTask(TaskManagementStep):
    """Cancel one queued or running task."""

    async def execute(self):
        manager, arguments = self.manager_and_arguments()
        self.context.response.answer = _answer(await manager.cancel(arguments["task_id"]))


@R.register("task_logs")
class TaskLogs(TaskManagementStep):
    """Read the trailing task log bytes."""

    async def execute(self):
        manager, arguments = self.manager_and_arguments()
        self.context.response.answer = await manager.logs(
            arguments["task_id"],
            arguments.get("limit", 65536),
        )
