import asyncio
import json
import os
import uuid
from threading import Event

import pytest

from axonx.app.components.agent.local_session_store import LocalAgentSessionStore


@pytest.mark.asyncio
async def test_local_session_store_round_trips_deduplicates_and_reopens(tmp_path):
    store = LocalAgentSessionStore(tmp_path / "sessions")
    session_id = str(uuid.uuid4())
    key = {"project_key": "workspace", "session_id": session_id}
    first = {
        "type": "user",
        "uuid": str(uuid.uuid4()),
        "timestamp": "2026-09-21T00:00:00Z",
        "unknown": {"preserved": True},
    }
    metadata = {"type": "custom-title", "customTitle": "Research"}

    await store.append(key, [first, metadata])
    await store.append(key, [first, metadata])

    reopened = LocalAgentSessionStore(tmp_path / "sessions")
    assert await reopened.load(key) == [first, metadata, metadata]
    assert [item["session_id"] for item in await reopened.list_sessions("workspace")] == [session_id]


@pytest.mark.asyncio
async def test_local_session_store_cascades_subkeys_on_delete(tmp_path):
    store = LocalAgentSessionStore(tmp_path / "sessions")
    session_id = str(uuid.uuid4())
    main = {"project_key": "workspace", "session_id": session_id}
    child = {**main, "subpath": "subagents/agent-one"}

    await store.append(main, [{"type": "user"}])
    await store.append(child, [{"type": "assistant"}])

    assert await store.list_subkeys(main) == ["subagents/agent-one"]
    await store.delete(main)
    assert await store.load(main) is None
    assert await store.load(child) is None


@pytest.mark.asyncio
async def test_local_session_store_rejects_path_traversal(tmp_path):
    store = LocalAgentSessionStore(tmp_path / "sessions")
    with pytest.raises(ValueError, match="project_key"):
        await store.load({"project_key": "../outside", "session_id": str(uuid.uuid4())})
    with pytest.raises(ValueError, match="subpath"):
        await store.load(
            {
                "project_key": "workspace",
                "session_id": str(uuid.uuid4()),
                "subpath": "../outside",
            }
        )


@pytest.mark.parametrize("field", ["project_key", "session_id", "subpath"])
@pytest.mark.parametrize("value", ["", ".", "..", "../outside", "/absolute", "nested/../outside"])
async def test_session_store_rejects_unsafe_keys(tmp_path, field, value):
    store = LocalAgentSessionStore(tmp_path / "sessions")
    key = {"project_key": "project", "session_id": "session", field: value}
    with pytest.raises(ValueError, match=field):
        await store.load(key)


async def test_session_store_rejects_symlinks_outside_root(tmp_path):
    root = tmp_path / "sessions"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "project").symlink_to(outside, target_is_directory=True)
    store = LocalAgentSessionStore(root)
    with pytest.raises(ValueError, match="leaves the store"):
        await store.append({"project_key": "project", "session_id": "session"}, [{"type": "user"}])
    assert not list(outside.iterdir())


async def test_session_store_preserves_dotted_subpaths(tmp_path):
    store = LocalAgentSessionStore(tmp_path)
    key = {"project_key": "project", "session_id": "session"}
    for name in ("agent.one", "agent.two"):
        await store.append({**key, "subpath": f"subagents/{name}"}, [{"type": "assistant", "uuid": name}])
    assert await store.list_subkeys(key) == ["subagents/agent.one", "subagents/agent.two"]
    assert await store.load({**key, "subpath": "subagents/agent.one"}) == [{"type": "assistant", "uuid": "agent.one"}]


async def test_failed_serialization_does_not_poison_deduplication(tmp_path):
    store = LocalAgentSessionStore(tmp_path)
    key = {"project_key": "project", "session_id": "session"}
    entry = {"type": "user", "uuid": "message"}
    with pytest.raises(TypeError):
        await store.append(key, [{**entry, "value": object()}])
    await store.append(key, [entry, entry])
    assert await store.load(key) == [entry]


async def test_disk_failure_retries_without_duplicate_entries(tmp_path, monkeypatch):
    store = LocalAgentSessionStore(tmp_path)
    key = {"project_key": "project", "session_id": "session"}
    entry = {"type": "user", "uuid": "message"}
    fsync = os.fsync

    def fail_once(descriptor):
        monkeypatch.setattr(os, "fsync", fsync)
        raise OSError("disk failure")

    monkeypatch.setattr(os, "fsync", fail_once)
    with pytest.raises(OSError, match="disk failure"):
        await store.append(key, [entry])
    await store.append(key, [entry])
    assert await store.load(key) == [entry]


async def test_cancelled_append_finishes_before_session_delete(tmp_path, monkeypatch):
    store = LocalAgentSessionStore(tmp_path)
    key = {"project_key": "project", "session_id": "session"}
    started, release = Event(), Event()

    def delayed_fsync(descriptor):
        started.set()
        assert release.wait(timeout=5)

    monkeypatch.setattr(os, "fsync", delayed_fsync)
    writing = asyncio.create_task(store.append(key, [{"type": "user"}]))
    try:
        assert await asyncio.to_thread(started.wait, 2)
        writing.cancel()
        deleting = asyncio.create_task(store.delete(key))
        await asyncio.sleep(0)
        assert not deleting.done()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await writing
    await deleting
    assert await store.load(key) is None


async def test_summary_validation_is_shared_by_load_and_list(tmp_path):
    store = LocalAgentSessionStore(tmp_path)
    key = {"project_key": "project", "session_id": "session"}
    await store.append(key, [{"type": "user"}])
    path = tmp_path / "project/session/summary.json"
    path.write_text(json.dumps({"session_id": "other", "mtime": 0, "data": {}}), encoding="utf-8")
    with pytest.raises(ValueError, match="summary"):
        await store.load_summary(key)
    with pytest.raises(ValueError, match="summary"):
        await store.list_summaries("project")
