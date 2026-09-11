"""Resolve executable Tasks from plugins and AxonX's registry."""

from importlib import import_module
from importlib.resources import files

from ..components.component_registry import R
from ..constants import PLUGIN_ENTRY_POINT_GROUP, PLUGIN_MANIFEST
from ..enumeration import ComponentEnum
from ..plugin.manifest import parse_plugin_manifest
from ..utils.entry_points import find_all_entry_points, load_entry_point
from .base_task import BaseTask


def _load_task(target: str) -> type[BaseTask]:
    module_name, qualname = target.split(":", 1)
    with R.preserve(allow_mutation=True):
        task_class = import_module(module_name)
        for part in qualname.split("."):
            task_class = getattr(task_class, part)
    if not isinstance(task_class, type) or not issubclass(task_class, BaseTask):
        raise TypeError(f"Task target must subclass BaseTask: {target}")
    return task_class


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
    tasks.update({name: _load_task(target) for name, target in plugin_targets.items()})
    return tasks


def resolve_task(name: str) -> type[BaseTask]:
    """Resolve one Task by name, preferring an installed plugin provider."""
    tasks = installed_tasks()
    task_class = tasks.get(name)
    if task_class is None:
        available = ", ".join(sorted(tasks)) or "none"
        raise ValueError(f"Unknown Task: {name}. Available: {available}")
    return task_class
