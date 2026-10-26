"""Exclusive leases for online publication."""

import fcntl
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def file_lock(path: Path):
    """Fail immediately when another process is publishing."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise BlockingIOError(f"Resource is busy: {path}") from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
