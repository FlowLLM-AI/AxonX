"""Task display-replica planning, transfer and application.

applier: Apply archives atomically and index verified installed replicas.
archive: Pack complete Task groups and build deterministic bounded archives.
artifacts: Discover, identify, validate and sample published display artifacts.
base: Component contract for replicating workspace task directories to a target service.
local: Reconcile and transfer selected workflow views using live or terminal rules.
models: Replica plans, transfer results, source-change errors and archive budget accounting.
replica: Prepare bounded, valid display artifacts without modifying source files.
"""

from . import applier, archive, artifacts, base, local, models, replica

__all__ = [
    "applier",
    "archive",
    "artifacts",
    "base",
    "local",
    "models",
    "replica",
]
