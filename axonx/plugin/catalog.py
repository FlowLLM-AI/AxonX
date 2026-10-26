"""Discover, resolve and describe built-in and installed plugin Tasks."""

from importlib import import_module, invalidate_caches
from inspect import cleandoc
from typing import Any

from ..task.builtins.demo import DemoTask
from ..task.builtins.dingtalk import SendDingTalkTask
from ..task.builtins.tushare import DownloadTushareTask
from ..task.core.base import BaseTask
from ..task.models.identity import TaskType
from ..task.models.query import TaskDefinition, TaskInfo
from .discovery import list_installed_plugins

BUILTIN_TASKS = {"demo": DemoTask, "send_dingtalk_task": SendDingTalkTask, "download_tushare_task": DownloadTushareTask}


class TaskCatalog:
    """A registration snapshot that loads Task classes only when requested."""

    def __init__(self) -> None:
        registrations: dict[str, tuple[type[BaseTask] | str, str | None]] = {
            name: (task, None) for name, task in BUILTIN_TASKS.items()
        }
        for plugin in list_installed_plugins():
            for name, target in plugin.tasks.items():
                if name in registrations:
                    owner = registrations[name][1]
                    if owner is None:
                        raise ValueError(f"Plugin Task names conflict with built-ins: {name}")
                    raise ValueError(f"Task {name!r} is provided by plugins {owner!r} and {plugin.distribution!r}")
                registrations[name] = target, plugin.distribution
        self._registrations = dict(sorted(registrations.items()))
        invalidate_caches()

    def resolve(self, name: str) -> type[BaseTask]:
        """Resolve and validate one Task, caching its class for this catalog."""
        if name not in self._registrations:
            available = ", ".join(self._registrations) or "none"
            raise ValueError(f"Unknown Task: {name}. Available: {available}")
        target, plugin = self._registrations[name]
        if not isinstance(target, str):
            return target
        module, separator, qualname = target.partition(":")
        if not module or not separator or not qualname:
            raise ValueError(f"Invalid Task target: {target!r}")
        value: Any = import_module(module)
        for part in qualname.split("."):
            value = getattr(value, part)
        if not isinstance(value, type) or not issubclass(value, BaseTask):
            raise TypeError(f"Task target must subclass BaseTask: {target}")
        self._registrations[name] = value, plugin
        return value

    def tasks(self) -> dict[str, type[BaseTask]]:
        """Load all registered Tasks in name order."""
        return {name: self.resolve(name) for name in self._registrations}

    def definitions(self, *, include_schemas: bool = True) -> list[TaskInfo]:
        """Describe every Task, generating parameter schemas only on request."""
        return [
            self.definition(name) if include_schemas else self._info(name, self.resolve(name))
            for name in self._registrations
        ]

    def definition(self, name: str) -> TaskDefinition:
        """Describe one Task without loading unrelated plugin Tasks."""
        task = self.resolve(name)
        return TaskDefinition(
            **self._info(name, task).model_dump(),
            input_schema=task.input_cls.model_json_schema(),
            output_schema=task.output_cls.model_json_schema(),
        )

    def _info(self, name: str, task: type[BaseTask]) -> TaskInfo:
        plugin = self._registrations[name][1]
        if not isinstance(task.task_type, TaskType):
            raise TypeError(f"Task {name!r} must declare a fixed TaskType")
        return TaskInfo(
            name=name,
            source="plugin" if plugin is not None else "native",
            plugin=plugin,
            task_type=task.task_type,
            description=cleandoc(task.__doc__ or ""),
        )
