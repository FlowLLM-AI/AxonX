"""Environment admission cannot leave unrelated requests waiting indefinitely."""

import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest

from axonx.plugin_kit import environment


def test_import_wait_is_bounded_and_releases_only_its_own_lease(monkeypatch):
    monkeypatch.setattr(environment, "_ENVIRONMENT_WAIT_SECONDS", 0.02)

    @environment.serialized
    def read():
        return "ready"

    with environment._ENVIRONMENT_LOCK, ThreadPoolExecutor(max_workers=1) as pool:
        with pytest.raises(TimeoutError, match="environment is busy"):
            pool.submit(read).result(timeout=1)
        assert read() == "ready"
    assert read() == "ready"


@pytest.mark.asyncio
async def test_expired_admission_does_not_block_later_operations(monkeypatch):
    monkeypatch.setattr(environment, "_ENVIRONMENT_WAIT_SECONDS", 0.02)
    entered, release = asyncio.Event(), asyncio.Event()

    @environment.environment_operation
    async def operation(wait=False):
        entered.set()
        if wait:
            await release.wait()
        return "ready"

    owner = asyncio.create_task(operation(wait=True))
    await entered.wait()
    try:
        with pytest.raises(TimeoutError, match="operation is busy"):
            await operation()
    finally:
        release.set()
        assert await owner == "ready"
    assert await operation() == "ready"
    assert not environment._OPERATION_QUEUE
