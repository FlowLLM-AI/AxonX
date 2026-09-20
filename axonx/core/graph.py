"""Dependency graph for application-owned components."""

from __future__ import annotations

import heapq
from collections.abc import Mapping

from ..components.base import BaseComponent

ComponentKey = tuple[str, str]


class ComponentGraph:
    """Validate, inject, and stably order application component dependencies."""

    def __init__(self, components: Mapping[str, Mapping[str, BaseComponent]]) -> None:
        self._nodes: dict[ComponentKey, BaseComponent] = {
            (category, name): component
            for category, group in components.items()
            for name, component in group.items()
        }

    def startup_order(self) -> tuple[BaseComponent, ...]:
        positions = {key: index for index, key in enumerate(self._nodes)}
        in_degree = dict.fromkeys(self._nodes, 0)
        dependants = {key: [] for key in self._nodes}

        for key, component in self._nodes.items():
            for dependency in component.dependencies:
                dependency_key = (dependency.component_type, dependency.name)
                if dependency_key not in self._nodes:
                    if not dependency.required:
                        continue
                    raise ValueError(
                        f"Component {key[0]}:{key[1]} depends on missing "
                        f"{dependency.component_type}:{dependency.name}",
                    )
                in_degree[key] += 1
                dependants[dependency_key].append(key)

        ready = [(positions[key], key) for key, degree in in_degree.items() if degree == 0]
        heapq.heapify(ready)
        ordered: list[BaseComponent] = []
        while ready:
            _, key = heapq.heappop(ready)
            ordered.append(self._nodes[key])
            for dependant in dependants[key]:
                in_degree[dependant] -= 1
                if in_degree[dependant] == 0:
                    heapq.heappush(ready, (positions[dependant], dependant))

        if len(ordered) != len(self._nodes):
            unresolved = [
                f"{key[0]}:{key[1]}" for key, degree in in_degree.items() if degree
            ]
            raise ValueError(
                "Components unresolved due to circular dependencies: "
                + ", ".join(unresolved)
            )

        for component in ordered:
            component.inject_dependencies(self._nodes)
        return tuple(ordered)
