"""Verify update admission, host isolation and response-completion handoff."""

import asyncio
from threading import Event
from unittest.mock import Mock

import pytest

from axonx.app.components.job.base import RESPONSE_CALLBACKS
from axonx.app.components.registry import ProviderRegistry
from axonx.app.components.updater.base import UpdateBackend
from axonx.app.components.updater.local import LocalUpdaterComponent
from axonx.app.config.models import ApplicationConfig
from axonx.app.core.context import ApplicationContext


@pytest.fixture
def backend():
    host = Mock(spec=UpdateBackend)
    host.prepare.return_value = {"update_id": "a" * 32}
    host.status.return_value = {"record": None, "log": ""}
    return host


@pytest.fixture
def updater(tmp_path, backend):
    context = ApplicationContext(ProviderRegistry(), ApplicationConfig(workspace_dir=str(tmp_path)), updates=backend)
    return LocalUpdaterComponent(app_context=context)


@pytest.fixture
def callbacks():
    pending = []
    token = RESPONSE_CALLBACKS.set(pending)
    try:
        yield pending
    finally:
        RESPONSE_CALLBACKS.reset(token)


@pytest.fixture
async def blocked_prepare(backend):
    loop = asyncio.get_running_loop()
    started, release = asyncio.Event(), Event()

    def prepare(_mode):
        loop.call_soon_threadsafe(started.set)
        if not release.wait(timeout=5):
            raise TimeoutError("Preparation was not released")
        return backend.prepare.return_value

    backend.prepare.side_effect = prepare
    try:
        yield started, release
    finally:
        release.set()


@pytest.mark.parametrize("mode", ["git", "pip", "restart"])
async def test_request_preserves_callbacks_and_defers_commit(updater, backend, callbacks, mode):
    existing = Mock()
    callbacks.append(existing)

    record = await updater.request(mode)

    assert record is backend.prepare.return_value
    backend.prepare.assert_called_once_with(mode)
    backend.commit.assert_not_called()
    assert callbacks[0] is existing
    assert len(callbacks) == 2
    assert updater.app_context.metadata["maintenance"]
    with pytest.raises(RuntimeError, match="already pending"):
        await updater.request(mode)
    assert len(callbacks) == 2

    callbacks[1]()

    backend.commit.assert_called_once_with(record["update_id"])
    existing.assert_not_called()
    assert updater.app_context.metadata["maintenance"]


async def test_request_without_a_response_boundary_has_no_side_effects(updater, backend):
    with pytest.raises(RuntimeError, match="response completion boundary"):
        await updater.request("restart")

    assert not updater.app_context.metadata
    assert not backend.mock_calls


@pytest.mark.parametrize("missing", ["context", "backend"])
async def test_missing_host_dependencies_fail_without_reserving_admission(updater, backend, callbacks, missing):
    context = updater.app_context
    if missing == "context":
        updater.app_context = None
        message = "requires an application context"
    else:
        context.updates = None
        message = "No update backend is configured"

    with pytest.raises(RuntimeError, match=message):
        await updater.request("restart")
    with pytest.raises(RuntimeError, match=message):
        updater.status()

    assert not context.metadata
    assert not callbacks
    assert not backend.mock_calls


async def test_failed_preparation_releases_admission_and_allows_retry(updater, backend, callbacks):
    updater.app_context.metadata["unrelated"] = "preserved"
    backend.prepare.side_effect = OSError("preparation failed")

    with pytest.raises(OSError, match="preparation failed"):
        await updater.request("git")

    assert updater.app_context.metadata == {"unrelated": "preserved"}
    assert not callbacks
    backend.commit.assert_not_called()

    backend.prepare.side_effect = None
    await updater.request("restart")
    assert len(callbacks) == 1
    assert updater.app_context.metadata["maintenance"]


@pytest.mark.parametrize("cancel", [False, True])
async def test_preparation_reserves_admission_across_instances_until_worker_finishes(
    updater, backend, callbacks, blocked_prepare, cancel
):
    started, release = blocked_prepare
    request = asyncio.create_task(updater.request("restart"))
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        if cancel:
            request.cancel()
            await asyncio.sleep(0)
            assert not request.done()

        other = LocalUpdaterComponent(app_context=updater.app_context)
        with pytest.raises(RuntimeError, match="already pending"):
            await other.request("pip")
        assert updater.app_context.metadata["maintenance"]
        backend.prepare.assert_called_once_with("restart")
        assert not callbacks
    finally:
        release.set()
        if request.cancelling():
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(request, timeout=5)
        else:
            await asyncio.wait_for(request, timeout=5)

    assert bool(updater.app_context.metadata.get("maintenance")) is not cancel
    assert len(callbacks) == (0 if cancel else 1)
    backend.commit.assert_not_called()


@pytest.mark.parametrize("update_id", [None, "b" * 32])
def test_status_remains_available_during_maintenance_without_a_response_boundary(updater, backend, update_id):
    updater.app_context.metadata["maintenance"] = True

    assert updater.status(update_id) is backend.status.return_value

    backend.status.assert_called_once_with(update_id)
    backend.prepare.assert_not_called()
    backend.commit.assert_not_called()
    assert updater.app_context.metadata == {"maintenance": True}
