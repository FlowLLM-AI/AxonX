"""Cooperative locks for shared workspace mutations and live Task directories."""

import asyncio
import fcntl
from contextlib import ExitStack, asynccontextmanager, contextmanager
from hashlib import sha256
from pathlib import Path


@contextmanager
def workspace_lock(root: Path, task_id: str | None = None, *, blocking: bool = False):
    """Fail fast on contention; lock files must survive Task resets and deletion.

    The workspace lock serializes directory mutations. A Task lock is held by
    its runner until cleanup finishes, including after terminal publication.
    """
    directory = root / ".locks"
    directory.mkdir(parents=True, exist_ok=True)
    name = sha256(task_id.encode()).hexdigest() if task_id is not None else "workspace"
    with (directory / name).open("a+b") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError as exc:
            raise BlockingIOError(f"Workspace is busy: {task_id or root}; retry the operation") from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


@asynccontextmanager
async def workspace_mutation(root: Path):
    """Wait for a directory mutation without blocking the event loop."""
    with ExitStack() as stack:
        while True:
            try:
                stack.enter_context(workspace_lock(root))
                break
            except BlockingIOError:
                await asyncio.sleep(0.01)
        yield
