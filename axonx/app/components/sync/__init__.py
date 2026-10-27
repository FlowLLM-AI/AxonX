"""Task display-replica planning, transfer and application.

applier: Validate and atomically apply display-replica archives.
archive: Build deterministic archives from prepared display-replica plans.
base: Component contract for replicating workspace task directories to a target service.
errors: Distinguish changing source snapshots from deterministic replica failures.
index: Source identities and verified replica indexes use the same transfer policy.
local: Reconcile and transfer bounded display replicas with opt-in live Task groups.
models: Internal replica plans and results owned by application synchronization.
planner: Select published task outputs and pack complete display replicas.
replica: Prepare bounded, valid display artifacts without modifying source files.
sampling: Bounded, whole-day Parquet sampling for read-only display replicas.
"""
