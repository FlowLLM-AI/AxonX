"""Validate Task names contributed by installed plugins."""

from dataclasses import dataclass

from .models import PluginInfo


@dataclass(frozen=True, slots=True)
class PluginContributions:
    tasks: dict[str, str]
    task_owners: dict[str, str]


def index_contributions(plugins: list[PluginInfo]) -> PluginContributions:
    tasks = {}
    owners = {}
    for plugin in plugins:
        for name, target in plugin.tasks.items():
            if name in owners:
                raise ValueError(f"Task {name!r} is provided by plugins {owners[name]!r} and {plugin.distribution!r}")
            tasks[name] = target
            owners[name] = plugin.distribution
    return PluginContributions(tasks, owners)
