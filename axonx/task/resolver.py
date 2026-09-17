"""Resolve executable Tasks from plugins and AxonX's registry."""

from copy import deepcopy
from importlib.resources import files
from inspect import cleandoc

from ..components.registry import R
from ..constants import PLUGIN_ENTRY_POINT_GROUP, PLUGIN_MANIFEST
from ..enums import ComponentEnum, TaskType
from ..plugin.manifest import parse_plugin_manifest
from ..schema import TaskDefinition
from ..utils.entry_points import find_all_entry_points, load_entry_point
from ..utils.imports import load_symbol
from .base import BaseTask


def _task_description(name: str, task_class: type[BaseTask]) -> str:
    description = task_class.__doc__
    if not description or not description.strip():
        raise TypeError(f"Task {name!r} must define a detailed class docstring")
    return cleandoc(description)


def installed_tasks() -> dict[str, type[BaseTask]]:
    """Return plugin Tasks first, falling back to built-in Tasks by name."""
    tasks = R.get_all(ComponentEnum.TASK)
    plugin_targets: dict[str, str] = {}
    for entry in find_all_entry_points(PLUGIN_ENTRY_POINT_GROUP):
        package = load_entry_point(entry)
        manifest = parse_plugin_manifest(
            files(package).joinpath(PLUGIN_MANIFEST).read_text(encoding="utf-8"),
            entry.name,
        )
        duplicate = plugin_targets.keys() & manifest.tasks.keys()
        if duplicate:
            names = ", ".join(sorted(duplicate))
            raise ValueError(f"Task provided by multiple plugins: {names}")
        plugin_targets.update(manifest.tasks)
    modules = {}
    tasks.update(
        {name: load_symbol(target, BaseTask, kind="Task", modules=modules) for name, target in plugin_targets.items()},
    )
    for name, task_class in tasks.items():
        _task_description(name, task_class)
    return tasks


def list_installed_task_definitions() -> list[TaskDefinition]:
    """Return sorted definitions for every installed Task."""
    definitions = []
    native_tasks = R.get_all(ComponentEnum.TASK)
    for name, task_class in sorted(installed_tasks().items()):
        task_type = task_class.task_type
        if not isinstance(task_type, TaskType):
            raise TypeError(f"Task {name!r} must declare a fixed TaskType")
        input_schema = deepcopy(task_class.input_cls.model_json_schema())
        definitions.append(
            TaskDefinition(
                name=name,
                source=("native" if native_tasks.get(name) is task_class else "plugin"),
                task_type=task_type,
                description=_task_description(name, task_class),
                input_schema=input_schema,
                output_schema=task_class.output_cls.model_json_schema(),
            ),
        )
    return definitions


def resolve_task(name: str) -> type[BaseTask]:
    """Resolve one Task by name, preferring an installed plugin provider."""
    tasks = installed_tasks()
    task_class = tasks.get(name)
    if task_class is None:
        available = ", ".join(sorted(tasks)) or "none"
        raise ValueError(f"Unknown Task: {name}. Available: {available}")
    return task_class
