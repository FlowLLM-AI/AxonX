"""Task observation: indexing, lineage, summaries and event streams.

base: Contract for Task metadata queries and local change notifications.
local: Periodically refreshed Task metadata index for application queries.
query: Snapshot filtering, bounded summaries and lazy lineage/context projections.
stream: Replay and follow a Task's durable progress and log streams.
"""

from . import base, local, query, stream

__all__ = [
    "base",
    "local",
    "query",
    "stream",
]
