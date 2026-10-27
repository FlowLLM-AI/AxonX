"""Verify transcript identity, deduplication and cancellation-safe Agent cleanup."""

import asyncio

import pytest

from axonx.app.components.agent.local_session_store import LocalAgentSessionStore
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
