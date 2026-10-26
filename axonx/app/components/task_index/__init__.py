"""Task observation: indexing, lineage, summaries and event streams.

base: Index contract and change notifications.
local: Local metadata polling, caching and component lifecycle.
graph: Connected lineage graphs and contextual Task relationships.
summary: Bounded list summaries and creation-time ordering.
stream: Durable progress replay and byte-offset log following.
"""

from . import base, graph, local, stream, summary
from .base import BaseTaskIndex
from .graph import TaskGraphQuery
from .local import LocalTaskIndex
from .stream import TaskEventStream
from .summary import summarize_status, task_sort_key

__all__ = [
    "BaseTaskIndex",
    "LocalTaskIndex",
    "TaskEventStream",
    "TaskGraphQuery",
    "base",
    "graph",
    "local",
    "stream",
    "summarize_status",
    "summary",
    "task_sort_key",
]
