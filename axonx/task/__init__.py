"""Task capabilities and their public package namespaces.

models: Shared data contracts, identity rules, parameters and validation.
storage: Task directories, records, artifacts, snapshots, journals and histories.
core: Synchronous Task authoring, composition, research bases and execution windows.
runtime: Task execution, progress, lifecycle, process control and replay drivers.
builtins: Bundled demo, notification, data-download and stock research implementations.
"""

from . import builtins, core, models, runtime, storage

__all__ = [
    "builtins",
    "core",
    "models",
    "runtime",
    "storage",
]
