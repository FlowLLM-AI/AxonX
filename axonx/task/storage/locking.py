"""Cooperative locks for shared workspace mutations and live Task directories."""

import asyncio
from contextlib import ExitStack, asynccontextmanager, contextmanager
from hashlib import sha256
from pathlib import Path
from time import monotonic

from ...utils.fs import file_lock


@contextmanager
def workspace_lock(root: Path, task_id: str | None = None, *, blocking: bool = False):
    """Fail fast on contention; lock files must survive Task resets and deletion.

    The workspace lock serializes directory mutations. A Task lock is held by
    its runner until cleanup finishes, including after terminal publication.
    """
    directory = root / ".locks"
    directory.mkdir(parents=True, exist_ok=True)
    name = sha256(task_id.encode()).hexdigest() if task_id is not None else "workspace"
    with ExitStack() as stack:
        try:
            stack.enter_context(file_lock(directory / name, timeout=30 if blocking else 0))
        except BlockingIOError as exc:
            raise BlockingIOError(f"Workspace is busy: {task_id or root}; retry the operation") from exc
        yield


@asynccontextmanager
async def workspace_mutation(root: Path):
    """Wait for a directory mutation without blocking the event loop."""
    with ExitStack() as stack:
        deadline = monotonic() + 30
        while True:
            try:
                stack.enter_context(workspace_lock(root))
                break
            except BlockingIOError:
                if monotonic() >= deadline:
                    raise TimeoutError(f"Workspace mutation wait exceeded 30s: {root}") from None
                await asyncio.sleep(0.01)
        yield
