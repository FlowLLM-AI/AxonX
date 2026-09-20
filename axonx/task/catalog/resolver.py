"""Resolve executable Tasks from plugins and AxonX's registry."""

from inspect import cleandoc
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from ...components.registry import ProviderRegistry
from ...enums import ComponentEnum, TaskType
from ...plugin_kit import index_contributions, list_installed_plugins
from ...plugin_kit.loading import load_symbol
from ..core.task import BaseTask


class TaskDefinition(BaseModel):
    """Describe an installed Task and its input and output schemas."""

    model_config = ConfigDict(frozen=True)
    name: str
    source: Literal["native", "plugin"]
    plugin: str | None = None
    task_type: TaskType
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]


def _task_description(name: str, task_class: type[BaseTask]) -> str:
    description = task_class.__doc__
    if not description or not description.strip():
        raise TypeError(f"Task {name!r} must define a detailed class docstring")
    return cleandoc(description)


def _plugin_task_targets() -> tuple[dict[str, str], dict[str, str]]:
    """Return plugin Task targets and their providers."""
    contributions = index_contributions(list_installed_plugins())
    return contributions.tasks, contributions.task_owners


def _task_catalog() -> tuple[dict[str, type[BaseTask]], dict[str, str]]:
    tasks = ProviderRegistry.from_builtins().get_all(ComponentEnum.TASK, BaseTask)
    plugin_targets, plugin_names = _plugin_task_targets()
    modules = {}
    tasks.update(
        {
            name: load_symbol(target, BaseTask, kind="Task", modules=modules)
            for name, target in plugin_targets.items()
        },
    )
    for name, task_class in tasks.items():
        _task_description(name, task_class)
    return tasks, plugin_names


def installed_tasks() -> dict[str, type[BaseTask]]:
    """Return built-in and installed plugin tasks."""
    return _task_catalog()[0]


def list_installed_task_definitions() -> list[TaskDefinition]:
    """Return sorted definitions for every installed Task."""
    definitions = []
    native_tasks = ProviderRegistry.from_builtins().get_all(
        ComponentEnum.TASK,
        BaseTask,
    )
    tasks, plugin_names = _task_catalog()
    for name, task_class in sorted(tasks.items()):
        task_type = task_class.task_type
        if not isinstance(task_type, TaskType):
            raise TypeError(f"Task {name!r} must declare a fixed TaskType")
        source = "native" if native_tasks.get(name) is task_class else "plugin"
        definitions.append(
            TaskDefinition(
                name=name,
                source=source,
                plugin=plugin_names.get(name) if source == "plugin" else None,
                task_type=task_type,
                description=_task_description(name, task_class),
                input_schema=task_class.input_cls.model_json_schema(),
                output_schema=task_class.output_cls.model_json_schema(),
            ),
        )
    return definitions


def resolve_task(name: str) -> type[BaseTask]:
    """Resolve only the requested Task so an unrelated broken plugin is isolated."""
    native = ProviderRegistry.from_builtins().get_all(ComponentEnum.TASK, BaseTask)
    if task_class := native.get(name):
        return task_class

    plugin_targets, _ = _plugin_task_targets()
    target = plugin_targets.get(name)
    if target is not None:
        task_class = load_symbol(target, BaseTask, kind="Task")
        _task_description(name, task_class)
        return task_class

    available = ", ".join(sorted(native.keys() | plugin_targets.keys())) or "none"
    raise ValueError(f"Unknown Task: {name}. Available: {available}")
