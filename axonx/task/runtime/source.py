"""Task provenance passed through command dispatch and worker environments."""

from contextvars import ContextVar

from ..schemas.lifecycle import TaskSource

TASK_SOURCE: ContextVar[TaskSource] = ContextVar("task_source", default=TaskSource(kind="submit"))
TASK_SOURCE_ENV = "AXONX_TASK_SOURCE"
