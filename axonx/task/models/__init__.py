"""Task data contracts, organized by responsibility.

base: Shared validation policy and calendar dates.
identity: Task types, states, names and dependency IDs.
artifacts: Artifact references, protocols, model collections and replay manifests.
lifecycle: Invocation context, child results, progress and persisted metadata.
params: Task inputs and output envelopes, including execution-window inputs.
reports: Training curves, comparisons, window outcomes, backtests and history.
query: Catalog definitions, summaries, graphs and context projections.
events: Log chunks and discriminated progress/log stream events.

Import each model from its owning module. This package does not load execution,
storage or business operations.
"""
