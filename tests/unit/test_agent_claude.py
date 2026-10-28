"""Exercise SDK boundaries without starting Claude or calling external services."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

from axonx.app.components.agent.claude.tools import JobToolServer
from axonx.app.components.agent.models import AGENT_DEPTH_ARGUMENT
from axonx.app.core.application import Application
from axonx.client.config import TARGET_ARGUMENT
from axonx.client.events import AgentMessageEvent, ResultEvent
from axonx.client.models import JobResponse


@pytest.fixture
def sdk_clients(monkeypatch):
    import claude_agent_sdk

    clients = []

    class Client:
        def __init__(self, options):
            self.options = options
            self.session_id = options.resume or options.session_id
            self.connect = AsyncMock()
            self.interrupt = AsyncMock()
            self.disconnect = AsyncMock()
            self.emit_result = True
            clients.append(self)

        async def query(self, message, *, session_id):
            assert session_id == self.session_id
            key = {
                "project_key": claude_agent_sdk.project_key_for_directory(self.options.cwd),
                "session_id": session_id,
            }
            await self.options.session_store.append(
                key,
                [
                    {
                        "type": "user",
                        "uuid": str(uuid4()),
                        "sessionId": session_id,
                        "parentUuid": None,
                        "timestamp": "2026-10-27T00:00:00Z",
                        "message": {"role": "user", "content": message},
                    }
                ],
            )

        async def receive_response(self):
            yield AssistantMessage(content=[TextBlock("answer")], model="test", uuid="assistant")
            if self.emit_result:
                yield ResultMessage(
                    subtype="success",
                    duration_ms=1,
                    duration_api_ms=1,
                    is_error=False,
                    num_turns=1,
                    session_id=self.session_id,
                    result="answer",
                    structured_output={"answer": 42},
                    terminal_reason="completed",
                )

    monkeypatch.setattr(claude_agent_sdk, "ClaudeSDKClient", Client)
    return clients


def make_app(tmp_path, **agent_options):
    return Application(
        workspace_dir=str(tmp_path),
        log_to_console=False,
        log_to_file=False,
        language="zh",
        environment={"FROM_APP": "app", "SHARED": "app"},
        components={"agent": {"default": {"backend": "claude", **agent_options}}},
    )


async def test_stream_and_folded_reply_preserve_session_options_and_guides(tmp_path, sdk_clients):
    (tmp_path / "prompt.md").write_text("Custom prompt", encoding="utf-8")
    app = make_app(
        tmp_path,
        system_prompt={"type": "file", "path": "prompt.md"},
        env={"SHARED": "agent"},
        session_store={"backend": "local", "path": "sessions"},
    )
    async with app:
        agent = app.context.components["agent"]["default"]
        events = [event async for event in agent.reply_stream("hello")]
        start, message, result_message, result = events
        assert isinstance(start, AgentMessageEvent)
        assert start.type_name == "SessionStart"
        assert [event.sequence for event in events[:-1]] == [0, 1, 2]
        assert message.role == "assistant"
        assert message.presentation[1].payload == {"text": "answer"}
        assert result_message.type_name == "ResultMessage"
        assert isinstance(result, ResultEvent)
        assert result.answer == {"answer": 42}
        assert result.metadata["session_id"] == start.session_id
        response = await agent.reply("again", session_id=start.session_id)
        assert response.answer == {"answer": 42}
        assert response.success
        first, second = (client.options for client in sdk_clients)
        assert first.session_id == start.session_id
        assert first.resume is None
        assert second.resume == start.session_id
        assert second.session_id is None
        assert first.include_partial_messages
        assert first.setting_sources == ["project"]
        assert first.env == {
            "FROM_APP": "app",
            "SHARED": "agent",
            "CLAUDE_CONFIG_DIR": str(tmp_path / "agent/claude/default"),
        }
        assert first.system_prompt == "Custom prompt\n\n" + agent.dev_guide
        assert agent.dev_guide.startswith("# AxonX 开发与运行指南")
        assert agent.sdk_store.root == tmp_path / "sessions"
        assert agent.options["system_prompt"] == {"type": "file", "path": "prompt.md"}
        assert agent.options["env"] == {"SHARED": "agent"}
    for client in sdk_clients:
        client.disconnect.assert_awaited_once()
        client.interrupt.assert_not_awaited()


async def test_cancel_and_missing_result_both_release_the_sdk_client(tmp_path, sdk_clients):
    async with make_app(tmp_path, load_dev_guide=False) as app:
        agent = app.context.components["agent"]["default"]
        stream = agent.reply_stream("hello")
        start = await anext(stream)
        with pytest.raises(RuntimeError, match="Cannot delete a running"):
            await agent.delete_session(start.session_id)
        await agent.cancel_turn(start.session_id)
        await stream.aclose()
        sdk_clients[0].disconnect.assert_awaited_once()
        assert sdk_clients[0].interrupt.await_count == 2
        with pytest.raises(KeyError, match="not running"):
            await agent.cancel_turn(start.session_id)

        missing = agent.reply_stream("hello")
        await anext(missing)
        sdk_clients[1].emit_result = False
        with pytest.raises(RuntimeError, match="no ResultMessage"):
            async for _event in missing:
                pass
        sdk_clients[1].interrupt.assert_awaited_once()
        sdk_clients[1].disconnect.assert_awaited_once()


async def test_turns_serialize_per_session_and_release_idle_locks(tmp_path, sdk_clients, monkeypatch):
    import claude_agent_sdk

    entered, release = asyncio.Event(), asyncio.Event()
    query = claude_agent_sdk.ClaudeSDKClient.query

    async def blocked_query(client, message, *, session_id):
        if message == "first":
            entered.set()
            await release.wait()
        await query(client, message, session_id=session_id)

    monkeypatch.setattr(claude_agent_sdk.ClaudeSDKClient, "query", blocked_query)
    async with make_app(tmp_path, load_dev_guide=False) as app:
        agent = app.context.components["agent"]["default"]
        session_id = (await agent.reply("seed")).metadata["session_id"]
        first = asyncio.create_task(agent.reply("first", session_id=session_id))
        second = None
        try:
            await asyncio.wait_for(entered.wait(), 2)
            second = asyncio.create_task(agent.reply("second", session_id=session_id))
            await asyncio.sleep(0)
            assert len(sdk_clients) == 2
            with pytest.raises(RuntimeError, match="Cannot delete a running"):
                await agent.delete_session(session_id)
            # Other sessions can complete while this session has a turn and a queued waiter.
            independent = await asyncio.wait_for(agent.reply("independent"), 2)
            assert independent.metadata["session_id"] != session_id
            release.set()
            responses = await asyncio.wait_for(asyncio.gather(first, second), 2)
            assert [response.metadata["session_id"] for response in responses] == [session_id, session_id]
            assert not agent._locks
        finally:
            release.set()
            for task in (first, second):
                if task is not None:
                    task.cancel()
            await asyncio.gather(first, *([second] if second is not None else []), return_exceptions=True)


async def test_shutdown_and_generator_close_share_one_disconnect(tmp_path, sdk_clients):
    async with make_app(tmp_path, load_dev_guide=False) as app:
        agent = app.context.components["agent"]["default"]
        stream = agent.reply_stream("hello")
        await anext(stream)
        client = sdk_clients[0]
        client.interrupt.side_effect = RuntimeError("already stopped")
        await agent.close()
        await stream.aclose()
        client.interrupt.assert_awaited_once()
        client.disconnect.assert_awaited_once()


async def test_closing_after_the_sdk_result_does_not_interrupt_a_completed_turn(tmp_path, sdk_clients):
    async with make_app(tmp_path, load_dev_guide=False) as app:
        agent = app.context.components["agent"]["default"]
        stream = agent.reply_stream("hello")
        await anext(stream)
        await anext(stream)
        result_message = await anext(stream)
        assert result_message.type_name == "ResultMessage"
        await stream.aclose()
        sdk_clients[0].interrupt.assert_not_awaited()
        sdk_clients[0].disconnect.assert_awaited_once()


async def test_connect_failure_still_releases_the_client(tmp_path, sdk_clients, monkeypatch):
    import claude_agent_sdk

    client_class = claude_agent_sdk.ClaudeSDKClient

    def failing_client(options):
        client = client_class(options)
        client.connect.side_effect = RuntimeError("connect failed")
        return client

    monkeypatch.setattr(claude_agent_sdk, "ClaudeSDKClient", failing_client)
    async with make_app(tmp_path, load_dev_guide=False) as app:
        agent = app.context.components["agent"]["default"]
        with pytest.raises(RuntimeError, match="connect failed"):
            await agent.reply("hello")
        sdk_clients[0].interrupt.assert_awaited_once()
        sdk_clients[0].disconnect.assert_awaited_once()
        assert not agent._active


async def test_file_prompt_and_explicit_config_directory_work_without_dev_guide(tmp_path, sdk_clients):
    (tmp_path / "prompt.md").write_text("Only this prompt", encoding="utf-8")
    async with make_app(
        tmp_path,
        load_dev_guide=False,
        system_prompt={"type": "file", "path": "prompt.md"},
        env={"CLAUDE_CONFIG_DIR": str(tmp_path / "custom-config")},
    ) as app:
        agent = app.context.components["agent"]["default"]
        await agent.reply("hello")
        assert sdk_clients[0].options.system_prompt == "Only this prompt"
        assert sdk_clients[0].options.env["CLAUDE_CONFIG_DIR"] == str(tmp_path / "custom-config")
        assert not (tmp_path / "agent/claude/default").exists()


@pytest.mark.parametrize("injected", [{}, {AGENT_DEPTH_ARGUMENT: {}}, {"other_system_argument": {}}])
async def test_job_tools_preserve_schemas_route_targets_and_inject_depth(monkeypatch, injected):
    import claude_agent_sdk

    captured = []

    def create_server(*, name, tools):
        assert name == "axonx"
        captured.extend(tools)
        return {"type": "sdk", "name": name}

    monkeypatch.setattr(claude_agent_sdk, "create_sdk_mcp_server", create_server)
    schema = {"type": "object", "properties": {"value": {"type": "integer"}}, "required": ["value"]}
    job = SimpleNamespace(name="job", description="Run job", parameters=schema, injected_parameters=injected)
    dispatcher = SimpleNamespace(run=AsyncMock(return_value=JobResponse(answer={"value": 2}, success=False)))
    server = JobToolServer([job], dispatcher)
    options = {"allowed_tools": ["Read", "mcp__axonx__job"], "mcp_servers": {"external": {"type": "http"}}}
    server.attach(options, depth=2)
    assert options["allowed_tools"] == ["Read", "mcp__axonx__job"]
    assert "external" in options["mcp_servers"]
    tool = captured[0]
    assert (TARGET_ARGUMENT in tool.input_schema["properties"]) == (not injected)
    assert TARGET_ARGUMENT not in schema["properties"]
    arguments = {"value": 1, **({TARGET_ARGUMENT: "host:1234"} if not injected else {})}
    result = await tool.handler(arguments)
    assert result == {"content": [{"type": "text", "text": '{"value":2}'}], "is_error": True}
    dispatcher.run.assert_awaited_once_with(
        "job",
        {"value": 1},
        system={AGENT_DEPTH_ARGUMENT: 3} if AGENT_DEPTH_ARGUMENT in injected else None,
        target="host:1234" if not injected else None,
    )
    if not injected:
        assert arguments[TARGET_ARGUMENT] == "host:1234"
    with pytest.raises(ValueError, match="reserved name"):
        server.attach(options, depth=2)


def test_job_tools_explain_incompatible_mcp_configuration():
    server = JobToolServer([], SimpleNamespace())
    with pytest.raises(ValueError, match="mcp_servers to be a mapping"):
        server.attach({"mcp_servers": "mcp.json"}, depth=0)
