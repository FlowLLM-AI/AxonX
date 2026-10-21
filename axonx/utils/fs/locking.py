"""Small, bounded leases for writers sharing a filesystem resource."""

import fcntl
import math
from contextlib import contextmanager
from pathlib import Path
from time import monotonic, sleep


@contextmanager
def file_lock(path: Path, *, timeout: float = 0, budget=None):
    """Fail immediately by default; an explicit wait always has a finite limit."""
    if not math.isfinite(timeout) or timeout < 0:
        raise ValueError("Lock timeout must be finite and nonnegative")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = monotonic() + timeout
    with path.open("a+b") as handle:
        while True:
            if budget is not None:
                budget.check()
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if timeout == 0:
                    raise BlockingIOError(f"Resource is busy: {path}") from None
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"Lock wait exceeded {timeout:g}s: {path}") from None
                delay = min(0.05, remaining)
                (sleep if budget is None else budget.sleep)(delay)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
