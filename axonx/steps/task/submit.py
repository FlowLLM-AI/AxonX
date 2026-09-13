"""Task-submission step."""

from ...components.registry import R
from ...constants import CLI_RAW_ARGUMENTS
from ...task.arguments import build_task_argv, split_task_arguments, task_name_from_argv
from ...task.resolver import resolve_task
from ..base import BaseStep


@R.register("submit_task")
class SubmitTaskStep(BaseStep):
    """Submit CLI-compatible or structured Task arguments to the manager."""

    async def execute(self):
        arguments = self.context.get(CLI_RAW_ARGUMENTS)
        if arguments is None:
            task_name, config = split_task_arguments(self.context)
            resolve_task(task_name).config_cls.model_validate(config)
            arguments = build_task_argv(task_name, config)
        else:
            task_name = self.context.get("task") or task_name_from_argv(arguments)
        await self.task_manager.submit(arguments)
        self.response.answer = {
            "accepted": True,
            "task": task_name,
        }
