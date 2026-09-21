import uuid

import pytest
from claude_agent_sdk import (
    delete_session_via_store,
    fork_session_via_store,
    get_session_messages_from_store,
    list_sessions_from_store,
    project_key_for_directory,
    rename_session_via_store,
    tag_session_via_store,
)
from claude_agent_sdk.testing import run_session_store_conformance

from axonx.components.agent.claude.session_store import ClaudeSessionStoreAdapter
from axonx.components.agent.local_session_store import LocalAgentSessionStore


@pytest.mark.asyncio
async def test_claude_adapter_satisfies_sdk_store_contract(tmp_path):
    counter = 0

    def make_store():
        nonlocal counter
        counter += 1
        return ClaudeSessionStoreAdapter(
            LocalAgentSessionStore(tmp_path / f"contract-{counter}")
        )

    await run_session_store_conformance(make_store)


@pytest.mark.asyncio
async def test_claude_adapter_supports_sdk_session_lifecycle(tmp_path):
    directory = str(tmp_path / "workspace")
    session_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    assistant_id = str(uuid.uuid4())
    store = ClaudeSessionStoreAdapter(LocalAgentSessionStore(tmp_path / "sessions"))
    key = {
        "project_key": project_key_for_directory(directory),
        "session_id": session_id,
    }
    await store.append(
        key,
        [
            {
                "type": "user",
                "uuid": user_id,
                "parentUuid": None,
                "sessionId": session_id,
                "timestamp": "2026-09-21T00:00:00Z",
                "cwd": directory,
                "message": {"role": "user", "content": "hello"},
            },
            {
                "type": "assistant",
                "uuid": assistant_id,
                "parentUuid": user_id,
                "sessionId": session_id,
                "timestamp": "2026-09-21T00:00:01Z",
                "cwd": directory,
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "hi"}],
                },
            },
        ],
    )

    sessions = await list_sessions_from_store(store, directory=directory)
    assert [item.session_id for item in sessions] == [session_id]
    messages = await get_session_messages_from_store(
        store, session_id, directory=directory
    )
    assert [item.type for item in messages] == ["user", "assistant"]

    await rename_session_via_store(store, session_id, "Renamed", directory=directory)
    await tag_session_via_store(store, session_id, "research", directory=directory)
    updated = await list_sessions_from_store(store, directory=directory)
    assert updated[0].custom_title == "Renamed"
    assert updated[0].tag == "research"

    forked = await fork_session_via_store(store, session_id, directory=directory)
    assert forked.session_id != session_id
    assert len(await list_sessions_from_store(store, directory=directory)) == 2

    await delete_session_via_store(store, session_id, directory=directory)
    remaining = await list_sessions_from_store(store, directory=directory)
    assert [item.session_id for item in remaining] == [forked.session_id]
