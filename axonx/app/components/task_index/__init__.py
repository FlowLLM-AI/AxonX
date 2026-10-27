"""Task observation: indexing, lineage, summaries and event streams.

base: Contract for Task metadata queries and local change notifications.
local: Periodically refreshed Task metadata index for application queries.
query: Bounded Task summaries and lineage/context projections from indexed metadata.
stream: Replay and follow a Task's durable progress and log streams.
"""
