"""Task-scoped log capture owned by the execution runtime."""

import fcntl
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
from datetime import datetime
from hashlib import sha256

from loguru import logger

from ...common.logging import get_log_path, log_file

_TASKS: ContextVar[tuple[str, ...]] = ContextVar("axonx_log_tasks", default=())


@contextmanager
def task_log_scope(task_id: str, started_at: datetime):
    """Capture one Task and its nested children without capturing siblings."""
    scope = f"{task_id}:{started_at.isoformat()}"
    tasks = (*_TASKS.get(), scope)
    token = _TASKS.set(tasks)
    try:
        with ExitStack() as stack:
            process_path = get_log_path()
            path = None
            if process_path is not None:
                identity = sha256(scope.encode("utf-8")).hexdigest()
                path = process_path.with_name(f"{process_path.stem}_{identity}.log")
                handle = stack.enter_context(path.open("ab"))
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                stack.enter_context(log_file(path, predicate=lambda record: scope in record["extra"].get("tasks", ())))
            with logger.contextualize(tasks=tasks):
                yield path
    finally:
        _TASKS.reset(token)
