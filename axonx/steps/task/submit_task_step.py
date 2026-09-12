"""Task-submission step."""

import json
from typing import Any

from ...components import R
from ...constants import CLI_RAW_ARGUMENTS
from ...task.task_resolver import resolve_task
from ..common.base_step import BaseStep


@R.register("submit_task")
class SubmitTaskStep(BaseStep):
    """Submit CLI-compatible or structured Task arguments to the manager."""

    async def execute(self):
        arguments = self.context.get(CLI_RAW_ARGUMENTS)
        if arguments is None:
            values = {key: value for key, value in self.context.items() if key != CLI_RAW_ARGUMENTS}
            task_name = values.get("task")
            if not isinstance(task_name, str) or not task_name:
                raise ValueError("task must be a non-empty string")
            resolve_task(task_name).config_cls.model_validate(
                {key: value for key, value in values.items() if key != "task"},
            )
            arguments = self._to_argv(values)
        await self.task_manager.submit(arguments)
        self.response.answer = {
            "accepted": True,
            "task": self.context.get("task", self._task_name(arguments)),
        }

    @classmethod
    def _to_argv(cls, values: dict[str, Any]) -> list[str]:
        """Encode structured HTTP values as lossless CLI option pairs."""
        task = values.get("task")
        if not isinstance(task, str) or not task:
            raise ValueError("task must be a non-empty string")
        arguments = ["--task", task]
        for key, value in values.items():
            if key == "task":
                continue
            arguments.extend((f"--{key.replace('_', '-')}", cls._encode(value)))
        return arguments

    @staticmethod
    def _encode(value: Any) -> str:
        if isinstance(value, str):
            return json.dumps(value, ensure_ascii=False)
        if value is None or isinstance(value, (bool, int, float, list, dict)):
            return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        raise TypeError(f"Unsupported Task argument type: {type(value).__name__}")

    @staticmethod
    def _task_name(arguments: list[str]) -> str | None:
        try:
            return arguments[arguments.index("--task") + 1]
        except (ValueError, IndexError):
            return None
