"""Task registration names and canonical task IDs."""

from __future__ import annotations

import re
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING

from ..constants import PLUGIN_MANIFEST
from ..enums import ComponentEnum, TaskType
from ..plugin.manifest import parse_plugin_manifest

if TYPE_CHECKING:
    from .base import BaseTask

_REG_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
_TASK_NAME = re.compile(r"^[A-Za-z0-9-]{1,32}$")
_TIMESTAMP = re.compile(r"^[0-9]{10}(?:[0-9]{4})?$")


def task_type_from_id(task_id: str) -> TaskType:
    """Read the task category from a canonical task ID."""
    if not isinstance(task_id, str) or Path(task_id).name != task_id:
        raise ValueError(f"Invalid task ID: {task_id!r}")
    parts = task_id.split("#")
    if len(parts) not in (3, 4) or not _REG_NAME.fullmatch(parts[1]) or not _TASK_NAME.fullmatch(parts[2]):
        raise ValueError(f"Invalid task ID: {task_id!r}")
    if len(parts) == 4 and not _TIMESTAMP.fullmatch(parts[3]):
        raise ValueError(f"Invalid task ID: {task_id!r}")
    try:
        return TaskType(parts[0])
    except ValueError:
        raise ValueError(f"Invalid task type in ID: {task_id!r}") from None


def registration_name(task_class: type[BaseTask], explicit: str | None) -> str:
    """Resolve a class's registry or manifest name and validate it."""
    name = explicit
    if name is None:
        from ..components.registry import R

        names = [key for key, cls in R.get_all(ComponentEnum.TASK).items() if cls is task_class]
        if len(names) > 1:
            raise ValueError(f"Task {task_class.__name__} has multiple registration names; pass reg_name")
        name = names[0] if names else _manifest_registration_name(task_class)
    if not name:
        raise ValueError(f"Task {task_class.__name__} has no registration name")
    if not _REG_NAME.fullmatch(name):
        raise ValueError(f"Invalid Task registration name: {name!r}")
    return name


def _manifest_registration_name(task_class: type[BaseTask]) -> str | None:
    module = task_class.__module__
    target = f"{module}:{task_class.__qualname__}"
    package = module.rpartition(".")[0]
    while package:
        manifest_file = files(package).joinpath(PLUGIN_MANIFEST)
        if manifest_file.is_file():
            manifest = parse_plugin_manifest(manifest_file.read_text(encoding="utf-8"), package)
            names = [name for name, value in manifest.tasks.items() if value == target]
            if len(names) > 1:
                raise ValueError(f"Task {task_class.__name__} has multiple registration names; pass reg_name")
            if names:
                return names[0]
        package = package.rpartition(".")[0]
    return None
