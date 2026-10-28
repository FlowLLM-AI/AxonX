"""Verify transcript identity, deduplication and cancellation-safe Agent cleanup."""

import asyncio

import pytest

from axonx.app.components.agent.session_store import LocalAgentSessionStore
from axonx.app.core.application import Application


@pytest.mark.asyncio
async def test_session_identity_does_not_require_loading_its_transcript(tmp_path, monkeypatch):
    store = LocalAgentSessionStore(tmp_path)
    key = {"project_key": "project", "session_id": "session"}
    assert not await store.exists(key)
    await store.append(key, [{"type": "user", "uuid": "one"}, {"type": "user", "uuid": "one"}])
    assert await store.load(key) == [{"type": "user", "uuid": "one"}]

    def refuse_read(_path):
        raise AssertionError("Identity lookup must not read transcript contents")

    monkeypatch.setattr(store, "_read", refuse_read)
    assert await store.exists(key)
    await store.delete(key)
    assert not await store.exists(key)


@pytest.mark.asyncio
async def test_repeated_cancellation_waits_for_agent_disconnect(tmp_path, monkeypatch):
    import claude_agent_sdk

    queried, disconnecting, release, disconnected = (asyncio.Event() for _ in range(4))

    class Client:
        def __init__(self, _options):
            pass

        async def connect(self):
            pass

        async def query(self, *_args, **_kwargs):
            queried.set()
            await asyncio.Event().wait()

        async def receive_response(self):
            yield None

        async def interrupt(self):
            pass

        async def disconnect(self):
            disconnecting.set()
            await release.wait()
            disconnected.set()

    monkeypatch.setattr(claude_agent_sdk, "ClaudeSDKClient", Client)
    app = Application(
        workspace_dir=str(tmp_path),
        log_to_console=False,
        log_to_file=False,
        components={"agent": {"default": {"backend": "claude", "load_dev_guide": False}}},
    )
    async with app:
        agent = app.context.components["agent"]["default"]
        stream = agent.reply_stream("hello")
        await anext(stream)
        turn = asyncio.create_task(anext(stream))
        try:
            await asyncio.wait_for(queried.wait(), 2)
            turn.cancel()
            await asyncio.wait_for(disconnecting.wait(), 2)
            turn.cancel()
            await asyncio.sleep(0)
            assert not turn.done()
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(turn, 2)
            assert disconnected.is_set()
        finally:
            release.set()
            turn.cancel()
            await asyncio.gather(turn, return_exceptions=True)
            await stream.aclose()


@pytest.mark.parametrize("part", ["..", ".", "", "a/b", "/tmp/session"])
@pytest.mark.parametrize("field", ["project_key", "session_id"])
async def test_session_keys_cannot_escape_the_store(tmp_path, field, part):
    key = {"project_key": "project", "session_id": "session", field: part}
    with pytest.raises(ValueError, match="Invalid Agent session"):
        await LocalAgentSessionStore(tmp_path).append(key, [{"type": "user"}])


async def test_subtranscripts_and_deduplication_survive_reopening_and_delete(tmp_path):
    key = {"project_key": "project", "session_id": "session"}
    subkey = {**key, "subpath": "subagents/agent"}
    entry = {"type": "user", "uuid": "one"}
    store = LocalAgentSessionStore(tmp_path)
    await store.append(key, [entry])
    await store.append(subkey, [entry])
    reopened = LocalAgentSessionStore(tmp_path)
    await reopened.append(key, [entry, {"type": "tag", "tag": "a"}, {"type": "tag", "tag": "a"}])
    assert await reopened.load(key) == [entry, {"type": "tag", "tag": "a"}, {"type": "tag", "tag": "a"}]
    assert await reopened.list_subkeys(key) == ["subagents/agent"]
    assert len(await reopened.list_sessions("project")) == 1
    await reopened.delete(subkey)
    assert await reopened.exists(key)
    assert await reopened.list_subkeys(key) == []
    await reopened.append(subkey, [entry])
    await reopened.delete(key)
    assert await reopened.list_sessions("project") == []
    assert await reopened.load(subkey) is None
    await reopened.append(key, [entry])
    assert await reopened.load(key) == [entry]


@pytest.mark.parametrize("subpath", ["../escape", "transcript", "nested//empty", "/absolute"])
async def test_invalid_subpaths_and_symlinks_are_rejected(tmp_path, subpath):
    store = LocalAgentSessionStore(tmp_path / "store")
    key = {"project_key": "project", "session_id": "session"}
    with pytest.raises(ValueError):
        await store.append({**key, "subpath": subpath}, [{"type": "user"}])
    outside = tmp_path / "outside"
    outside.mkdir()
    store.root.mkdir()
    (store.root / "project").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="leaves the store"):
        await store.append(key, [{"type": "user"}])


async def test_claude_summary_uses_only_committed_entries_and_rebuilds_missing_sidecars(tmp_path):
    from axonx.app.components.agent.claude.session_store import ClaudeSessionStore

    key = {"project_key": "project", "session_id": "session"}
    old = {"type": "custom-title", "uuid": "old", "customTitle": "Old"}
    latest = {"type": "custom-title", "uuid": "latest", "customTitle": "Latest"}
    store = ClaudeSessionStore(tmp_path)
    await store.append(key, [old, latest])
    await store.append(key, [old])
    await store.append({**key, "subpath": "subagents/agent"}, [old])
    summaries = await store.list_session_summaries("project")
    assert len(summaries) == 1
    assert summaries[0]["data"]["custom_title"] == "Latest"
    assert summaries[0]["mtime"] == (await store.list_sessions("project"))[0]["mtime"]
    (tmp_path / "project/session/summary.json").unlink()
    await ClaudeSessionStore(tmp_path).append(key, [old])
    assert (await store.list_session_summaries("project"))[0]["data"]["custom_title"] == "Latest"


async def test_failed_summary_publication_can_retry_without_losing_entries(tmp_path, monkeypatch):
    from axonx.app.components.agent.claude.session_store import ClaudeSessionStore

    key = {"project_key": "project", "session_id": "session"}
    store = ClaudeSessionStore(tmp_path)
    await store.append(key, [{"type": "custom-title", "uuid": "old", "customTitle": "Old"}])
    latest = {"type": "custom-title", "uuid": "latest", "customTitle": "Latest"}
    with monkeypatch.context() as patch:

        def fail_save(*_args):
            raise OSError("disk error")

        patch.setattr(store, "_save_summary", fail_save)
        with pytest.raises(OSError, match="disk error"):
            await store.append(key, [latest])
    assert await store.list_session_summaries("project") == []
    await store.append(key, [latest])
    assert len(await store.load(key)) == 2
    assert (await store.list_session_summaries("project"))[0]["data"]["custom_title"] == "Latest"


async def test_duplicate_entries_do_not_republish_a_current_summary(tmp_path, monkeypatch):
    from axonx.app.components.agent.claude.session_store import ClaudeSessionStore

    store = ClaudeSessionStore(tmp_path)
    key = {"project_key": "project", "session_id": "session"}
    entry = {"type": "custom-title", "uuid": "title", "customTitle": "Title"}
    await store.append(key, [entry])

    def refuse_save(*_args):
        raise AssertionError("Duplicate entries must not rewrite a current summary")

    monkeypatch.setattr(store, "_save_summary", refuse_save)
    await store.append(key, [entry])
    assert (await store.list_session_summaries("project"))[0]["data"]["custom_title"] == "Title"


async def test_orphan_summary_is_rebuilt_for_a_new_transcript(tmp_path):
    from axonx.app.components.agent.claude.session_store import ClaudeSessionStore

    key = {"project_key": "project", "session_id": "session"}
    await ClaudeSessionStore(tmp_path).append(key, [{"type": "custom-title", "uuid": "old", "customTitle": "Old"}])
    (tmp_path / "project/session/transcript.jsonl").unlink()
    store = ClaudeSessionStore(tmp_path)
    await store.append(key, [{"type": "custom-title", "uuid": "new", "customTitle": "New"}])
    assert (await store.list_session_summaries("project"))[0]["data"]["custom_title"] == "New"
    assert len(await store.load(key)) == 1


async def test_cancellation_finishes_summary_before_a_queued_delete(tmp_path, monkeypatch):
    import threading

    from axonx.app.components.agent.claude.session_store import ClaudeSessionStore

    entered, release = threading.Event(), threading.Event()
    store = ClaudeSessionStore(tmp_path)
    key = {"project_key": "project", "session_id": "session"}
    save_summary = store._save_summary

    def delayed_save(*args):
        entered.set()
        if not release.wait(5):
            raise TimeoutError("summary was not released")
        save_summary(*args)

    monkeypatch.setattr(store, "_save_summary", delayed_save)
    append = asyncio.create_task(store.append(key, [{"type": "user", "uuid": "one"}]))
    delete = None
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        append.cancel()
        delete = asyncio.create_task(store.delete(key))
        await asyncio.sleep(0)
        assert not append.done()
        assert not delete.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(append, 2)
        await asyncio.wait_for(delete, 2)
        assert not await store.exists(key)
        assert await store.list_session_summaries("project") == []
    finally:
        release.set()
        await asyncio.gather(append, *([delete] if delete else []), return_exceptions=True)


async def test_agent_session_operations_use_the_same_persisted_sdk_session(tmp_path):
    from uuid import uuid4

    from claude_agent_sdk import project_key_for_directory

    session_id, user_id, assistant_id = (str(uuid4()) for _ in range(3))
    app = Application(
        workspace_dir=str(tmp_path),
        log_to_console=False,
        log_to_file=False,
        components={"agent": {"default": {"backend": "claude", "load_dev_guide": False}}},
    )
    async with app:
        agent = app.context.components["agent"]["default"]
        key = {"project_key": project_key_for_directory(tmp_path), "session_id": session_id}
        await agent.sdk_store.append(
            key,
            [
                {
                    "type": "user",
                    "uuid": user_id,
                    "parentUuid": None,
                    "sessionId": session_id,
                    "timestamp": "2026-10-27T00:00:00Z",
                    "message": {"role": "user", "content": "hello"},
                },
                {
                    "type": "assistant",
                    "uuid": assistant_id,
                    "parentUuid": user_id,
                    "sessionId": session_id,
                    "timestamp": "2026-10-27T00:00:01Z",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {"type": "text", "text": "answer"},
                        ],
                    },
                },
            ],
        )
        assert [item.session_id for item in await agent.list_sessions()] == [session_id]
        assert [block.text for block in (await agent.get_session(session_id)).blocks] == ["hello", "answer"]
        assert [block.text for block in (await agent.get_session(session_id, offset=1, limit=1)).blocks] == ["answer"]
        await agent.rename_session(session_id, "Renamed")
        await agent.tag_session(session_id, "important")
        info = (await agent.list_sessions())[0]
        assert info.custom_title == "Renamed"
        assert info.tag == "important"
        forked = await agent.fork_session(session_id, up_to_message_id=user_id, title="Fork")
        assert forked != session_id
        assert [block.text for block in (await agent.get_session(forked)).blocks] == ["hello"]
        await agent.tag_session(session_id, None)
        assert (await agent.get_session(session_id)).info.tag is None
        await agent.delete_session(session_id)
        assert [item.session_id for item in await agent.list_sessions()] == [forked]
        with pytest.raises(KeyError, match="not found"):
            await agent.get_session(session_id)
