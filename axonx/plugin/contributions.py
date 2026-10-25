"""Validate Task names contributed by installed plugins."""

from .models import PluginContributions, PluginInfo


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
