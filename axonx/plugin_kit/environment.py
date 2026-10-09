"""Coordinate plugin environment mutations and refresh future Task imports."""

from __future__ import annotations

import asyncio
import sys
from functools import wraps
from importlib import invalidate_caches, metadata
from threading import RLock
from typing import TYPE_CHECKING, Awaitable, Callable, Concatenate
from weakref import WeakKeyDictionary

from packaging.utils import canonicalize_name

from ..constants import PLUGIN_ENTRY_POINT_GROUP

if TYPE_CHECKING:
    from ..components.base import ComponentBase
    from ..core.context import ApplicationContext

_ENVIRONMENT_LOCK = RLock()
_APPLICATION_LOCKS: WeakKeyDictionary[ApplicationContext, asyncio.Lock] = WeakKeyDictionary()
_RESTART_REQUIRED = False


def serialized[T, **P](function: Callable[P, T]) -> Callable[P, T]:
    """Keep discovery and imports out of an in-progress plugin mutation."""

    @wraps(function)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> T:
        with _ENVIRONMENT_LOCK:
            return function(*args, **kwargs)

    return wrapped


def environment_operation[T, **P](
    function: Callable[Concatenate["ComponentBase", P], Awaitable[T]],
) -> Callable[Concatenate["ComponentBase", P], Awaitable[T]]:
    """Coordinate remote mutations with submission through worker launch."""

    @wraps(function)
    async def wrapped(component: "ComponentBase", *args: P.args, **kwargs: P.kwargs) -> T:
        context = component.app_context
        if context is None:
            return await function(component, *args, **kwargs)
        lock = _APPLICATION_LOCKS.setdefault(context, asyncio.Lock())
        async with lock:
            return await function(component, *args, **kwargs)

    return wrapped


def plugin_packages() -> set[str]:
    """Read declared plugin package ownership without importing code."""
    return {
        entry.value
        for distribution in metadata.distributions()
        for entry in distribution.entry_points
        if entry.group == PLUGIN_ENTRY_POINT_GROUP and ":" not in entry.value
    }


@serialized
def refresh_plugin_imports(packages: set[str]) -> None:
    """Forget plugin packages and helpers, including cross-plugin imports.

    Existing objects keep their classes. Subsequent resolution imports fresh
    objects. AxonX and third-party dependencies retain their module identities.
    Callers hold the environment lock across mutation and refresh.
    """
    packages = {name for name in packages if name != "axonx" and not name.startswith("axonx.")}
    for name in sorted(tuple(sys.modules), key=len, reverse=True):
        if not any(name == package or name.startswith(f"{package}.") for package in packages):
            continue
        module = sys.modules.pop(name, None)
        parent_name, _, child_name = name.rpartition(".")
        parent = sys.modules.get(parent_name)
        if parent is not None and module is not None and getattr(parent, child_name, None) is module:
            delattr(parent, child_name)
    invalidate_caches()


def distribution_versions() -> dict[str, str]:
    """Snapshot the first distribution on sys.path, matching discovery."""
    versions = {}
    for distribution in metadata.distributions():
        name = distribution.metadata.get("Name")
        if name:
            versions.setdefault(canonicalize_name(name), distribution.version)
    return versions


def record_dependency_changes(before: dict[str, str], plugin: str) -> None:
    """Keep a restart hint until process exit if pip replaced a dependency."""
    global _RESTART_REQUIRED
    target = canonicalize_name(plugin)
    _RESTART_REQUIRED |= any(
        name != target and name in before and version != before[name]
        for name, version in distribution_versions().items()
    )


def mark_restart_required(required: bool) -> bool:
    """Keep pending live-contribution/dependency changes until process exit."""
    global _RESTART_REQUIRED
    _RESTART_REQUIRED |= required
    return _RESTART_REQUIRED
