"""Validate and index contributions from installed plugins."""

from dataclasses import dataclass

from ..config import JobConfig
from .models import PluginInfo


@dataclass(frozen=True, slots=True)
class PluginContributions:
    tasks: dict[str, str]
    task_owners: dict[str, str]
    jobs: dict[str, JobConfig]
    components: dict[str, dict[str, str]]
    component_owners: dict[tuple[str, str], str]


def index_contributions(plugins: list[PluginInfo]) -> PluginContributions:
    """Merge plugin contributions and reject ambiguous public names."""
    tasks: dict[str, str] = {}
    jobs: dict[str, JobConfig] = {}
    components: dict[str, dict[str, str]] = {}
    task_owners: dict[str, str] = {}
    job_owners: dict[str, str] = {}
    component_owners: dict[tuple[str, str], str] = {}

    for plugin in plugins:
        owner = plugin.distribution
        for name, target in plugin.tasks.items():
            if name in task_owners:
                raise ValueError(
                    f"Task {name!r} is provided by plugins {task_owners[name]!r} and {owner!r}"
                )
            tasks[name] = target
            task_owners[name] = owner
        for name, config in plugin.jobs.items():
            if name in job_owners:
                raise ValueError(
                    f"Job {name!r} is provided by plugins {job_owners[name]!r} and {owner!r}"
                )
            jobs[name] = config.model_copy(deep=True)
            job_owners[name] = owner
        for component_type, backends in plugin.components.items():
            registered = components.setdefault(component_type, {})
            for backend, target in backends.items():
                identity = (component_type, backend)
                if identity in component_owners:
                    raise ValueError(
                        f"Component backend {component_type}:{backend} is provided by "
                        f"plugins {component_owners[identity]!r} and {owner!r}",
                    )
                registered[backend] = target
                component_owners[identity] = owner
    return PluginContributions(tasks, task_owners, jobs, components, component_owners)
