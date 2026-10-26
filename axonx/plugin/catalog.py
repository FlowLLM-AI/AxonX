"""Resolve executable Tasks from plugins and AxonX's registry."""

from inspect import cleandoc

from ..task.builtins.demo import DemoTask
from ..task.builtins.dingtalk import SendDingTalkTask
from ..task.builtins.tushare import DownloadTushareTask
from ..task.core.task import BaseTask
from ..task.models.identity import TaskType
from ..task.models.query import TaskDefinition, TaskInfo
from .contributions import index_contributions
from .discovery import list_installed_plugins
from .loading import load_symbol

BUILTIN_TASKS = {"demo": DemoTask, "send_dingtalk_task": SendDingTalkTask, "download_tushare_task": DownloadTushareTask}


def _task_catalog(
    name: str | None = None,
) -> dict[str, tuple[type[BaseTask], str | None]]:
    """Discover registrations, then load all Tasks or only the requested one."""
    native = dict(BUILTIN_TASKS)
    plugins = index_contributions(list_installed_plugins())
    duplicates = native.keys() & plugins.tasks.keys()
    if duplicates:
        raise ValueError(f"Plugin Task names conflict with built-ins: {', '.join(sorted(duplicates))}")
    targets = native | plugins.tasks
    if name is not None:
        if name not in targets:
            available = ", ".join(sorted(targets)) or "none"
            raise ValueError(f"Unknown Task: {name}. Available: {available}")
        targets = {name: targets[name]}
    modules = {}
    tasks = {}
    for task_name, target in sorted(targets.items()):
        task_class = load_symbol(target, BaseTask, kind="Task", modules=modules) if isinstance(target, str) else target
        tasks[task_name] = task_class, plugins.task_owners.get(task_name)
    return tasks


def installed_tasks() -> dict[str, type[BaseTask]]:
    """Return built-in and installed plugin tasks for local execution."""
    return {name: task for name, (task, _) in _task_catalog().items()}


def list_installed_task_definitions(*, include_schemas: bool = True) -> list[TaskInfo]:
    """Return sorted definitions, generating schemas only when requested."""
    describe = _task_definition if include_schemas else _task_info
    return [describe(name, task, plugin) for name, (task, plugin) in _task_catalog().items()]


def _task_info(name: str, task_class: type[BaseTask], plugin: str | None) -> TaskInfo:
    task_type = task_class.task_type
    if not isinstance(task_type, TaskType):
        raise TypeError(f"Task {name!r} must declare a fixed TaskType")
    return TaskInfo(
        name=name,
        source="plugin" if plugin is not None else "native",
        plugin=plugin,
        task_type=task_type,
        category=task_class.category,
        description=cleandoc(task_class.__doc__ or "").strip(),
    )


def _task_definition(name: str, task_class: type[BaseTask], plugin: str | None) -> TaskDefinition:
    return TaskDefinition(
        **_task_info(name, task_class, plugin).model_dump(),
        input_schema=task_class.input_cls.model_json_schema(),
        output_schema=task_class.output_cls.model_json_schema(),
    )


def get_task_definition(name: str) -> TaskDefinition:
    """Describe one registered Task without loading unrelated plugin Tasks."""
    task, plugin = _task_catalog(name)[name]
    return _task_definition(name, task, plugin)


def resolve_task(name: str) -> type[BaseTask]:
    """Resolve one Task using the same registrations as definition queries."""
    return _task_catalog(name)[name][0]
