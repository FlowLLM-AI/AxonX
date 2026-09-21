import uuid

import pytest

from axonx.components.agent.local_session_store import LocalAgentSessionStore


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
    assert [item["session_id"] for item in await reopened.list_sessions("workspace")] == [
        session_id
    ]


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
