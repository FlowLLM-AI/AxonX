"""Coordinate plugin environment mutations and refresh future Task imports."""

from __future__ import annotations

import asyncio
import sys
from collections import deque
from concurrent.futures import Future
from functools import wraps
from importlib import invalidate_caches, metadata
from pathlib import Path
from threading import Lock, RLock
from typing import Awaitable, Callable

from packaging.utils import canonicalize_name

from ..constants import PLUGIN_ENTRY_POINT_GROUP

_ENVIRONMENT_LOCK = RLock()
_OPERATION_QUEUE_LOCK = Lock()
_OPERATION_QUEUE: deque[Future[None]] = deque()
_RESTART_REQUIRED = False


def serialized[T, **P](function: Callable[P, T]) -> Callable[P, T]:
    """Keep discovery and imports out of an in-progress plugin mutation."""

    @wraps(function)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> T:
        with _ENVIRONMENT_LOCK:
            return function(*args, **kwargs)

    return wrapped


def environment_operation[T, **P](function: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
    """Serialize remote mutations and worker launch across applications and loops."""

    @wraps(function)
    async def wrapped(*args: P.args, **kwargs: P.kwargs) -> T:
        ticket: Future[None] = Future()
        with _OPERATION_QUEUE_LOCK:
            _OPERATION_QUEUE.append(ticket)
            if len(_OPERATION_QUEUE) == 1:
                ticket.set_result(None)
        try:
            await asyncio.shield(asyncio.wrap_future(ticket))
            return await function(*args, **kwargs)
        finally:
            with _OPERATION_QUEUE_LOCK:
                was_owner = _OPERATION_QUEUE[0] is ticket
                _OPERATION_QUEUE.remove(ticket)
                if was_owner and _OPERATION_QUEUE:
                    _OPERATION_QUEUE[0].set_result(None)

    return wrapped


async def run_in_thread[T, **P](function: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    """Drain an already-started operation before propagating cancellation."""
    task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        completion = asyncio.gather(task, return_exceptions=True)
        while not completion.done():
            try:
                await asyncio.shield(completion)
            except asyncio.CancelledError:
                pass
        raise


def plugin_modules() -> set[str]:
    """Collect declared packages and loaded modules owned by plugin wheels."""
    packages: set[str] = set()
    owned_files: set[Path] = set()
    for distribution in metadata.distributions():
        entries = [entry for entry in distribution.entry_points if entry.group == PLUGIN_ENTRY_POINT_GROUP]
        if not entries:
            continue
        packages.update(entry.value for entry in entries if ":" not in entry.value)
        owned_files.update(Path(distribution.locate_file(file)).resolve() for file in distribution.files or ())
    for name, module in tuple(sys.modules.items()):
        filename = getattr(module, "__file__", None)
        if isinstance(filename, str) and Path(filename).resolve() in owned_files:
            packages.add(name)
    return packages


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
