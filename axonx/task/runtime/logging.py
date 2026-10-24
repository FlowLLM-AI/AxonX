"""Run-scoped log capture owned by the Task execution runtime."""

import fcntl
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
from hashlib import sha256

from loguru import logger

from ...common.logging import get_log_path, log_file

_TASK_RUNS: ContextVar[tuple[str, ...]] = ContextVar("axonx_log_task_runs", default=())


@contextmanager
def task_log_scope(run_id: str):
    """Capture one Run and its nested children without capturing sibling Runs."""
    runs = (*_TASK_RUNS.get(), run_id)
    token = _TASK_RUNS.set(runs)
    try:
        with ExitStack() as stack:
            process_path = get_log_path()
            path = None
            if process_path is not None:
                identity = sha256(run_id.encode("utf-8")).hexdigest()
                path = process_path.with_name(f"{process_path.stem}_{identity}.log")
                handle = stack.enter_context(path.open("ab"))
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                stack.enter_context(
                    log_file(path, predicate=lambda record: run_id in record["extra"].get("task_runs", ()))
                )
            with logger.contextualize(task_runs=runs):
                yield path
    finally:
        _TASK_RUNS.reset(token)
