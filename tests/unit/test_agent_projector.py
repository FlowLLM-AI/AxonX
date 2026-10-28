"""Verify display blocks across partial messages, complete messages and stored history."""

from dataclasses import asdict

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    ServerToolResultBlock,
    ServerToolUseBlock,
    SessionMessage,
    StreamEvent,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from axonx.app.components.agent.claude.projector import ClaudeMessageProjector


def stream(projector, event):
    return projector.project(StreamEvent(uuid="stream", session_id="session", event=event))


@pytest.mark.parametrize(("kind", "field"), [("text", "text"), ("thinking", "thinking")])
def test_partial_text_is_reconciled_without_duplicate_blocks(kind, field):
    projector = ClaudeMessageProjector()
    stream(projector, {"type": "message_start"})
    start = stream(projector, {"type": "content_block_start", "index": 0, "content_block": {"type": kind, field: ""}})
    delta = stream(
        projector, {"type": "content_block_delta", "index": 0, "delta": {"type": f"{kind}_delta", field: "part"}}
    )
    stop = stream(projector, {"type": "content_block_stop", "index": 0})
    block = TextBlock("complete") if kind == "text" else ThinkingBlock("complete", "signature")
    complete = projector.project(AssistantMessage(content=[block], model="test", uuid="complete"))

    assert start[0].operation == "start"
    assert delta[0].delta == "part"
    assert stop[0].operation == "finish"
    assert len(complete) == 1
    assert complete[0].operation == "replace"
    assert complete[0].payload == {"text": "complete"}
    assert {patch.block_id for patch in [*start, *delta, *stop, *complete]} == {"stream:0"}
    assert projector.finish_open() == []

    # New messages may reuse a block index without modifying an earlier block.
    subsequent = projector.project(AssistantMessage(content=[TextBlock("next")], model="test", uuid="next"))
    assert subsequent[0].block_id == "next:0"
    assert subsequent[0].operation == "start"


@pytest.mark.parametrize(("server_tool", "failed"), [(False, False), (False, True), (True, False)])
def test_tools_share_result_semantics_in_streams_and_history(server_tool, failed):
    projector = ClaudeMessageProjector()
    use_type = "server_tool_use" if server_tool else "tool_use"
    stream(
        projector,
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": use_type, "id": "tool", "name": "web_search", "input": {}},
        },
    )
    deltas = stream(
        projector,
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "input_json_delta", "partial_json": '{"q":"hi"}'},
        },
    )
    assert deltas[0].delta == '{"q":"hi"}'
    assert deltas[0].payload == {}
    stop = stream(projector, {"type": "content_block_stop", "index": 0})
    assert stop[0].payload == {"status": "running"}
    use = (ServerToolUseBlock if server_tool else ToolUseBlock)(id="tool", name="web_search", input={"q": "hi"})
    result = (
        ServerToolResultBlock(tool_use_id="tool", content={"answer": "ok"})
        if server_tool
        else ToolResultBlock(tool_use_id="tool", content="ok", is_error=failed)
    )
    complete = projector.project(AssistantMessage(content=[use], model="test", uuid="assistant"))
    assert all(patch.operation != "start" for patch in complete)
    assert complete[-1].payload["text"] == ""
    assert complete[-1].payload["input"] == {"q": "hi"}
    terminal = projector.project(UserMessage(content=[result], uuid="result"))
    assert terminal[0].payload["status"] == ("failed" if failed else "succeeded")
    assert projector.finish_open(cancelled=True) == []

    history = ClaudeMessageProjector.history(
        [
            SessionMessage(
                type="assistant",
                uuid="assistant",
                session_id="session",
                message={"content": [{"type": use_type, **asdict(use)}]},
            ),
            SessionMessage(
                type="user",
                uuid="result",
                session_id="session",
                message={
                    "content": [{"type": "server_tool_result" if server_tool else "tool_result", **asdict(result)}]
                },
            ),
        ]
    )
    assert len(history) == 1
    assert history[0].block_id == "tool"
    assert history[0].message_uuid == "assistant"
    assert history[0].role == "assistant"
    assert history[0].status == terminal[0].payload["status"]
    assert history[0].payload == {"name": "web_search", "input": {"q": "hi"}, "result": result.content}
    assert history[0].text == ""


@pytest.mark.parametrize("cancelled", [False, True])
def test_unfinished_tools_close_once_at_the_end_of_a_turn(cancelled):
    projector = ClaudeMessageProjector()
    patches = projector.project(
        AssistantMessage(
            content=[TextBlock("hello"), ToolUseBlock(id="tool", name="python", input={})],
            model="test",
            uuid="message",
        )
    )
    assert [(patch.block_type, patch.operation) for patch in patches[:3]] == [
        ("text", "start"),
        ("text", "replace"),
        ("text", "finish"),
    ]
    terminal = projector.finish_open(cancelled=cancelled)
    assert len(terminal) == 1
    assert terminal[0].block_id == "tool"
    assert terminal[0].payload["status"] == ("cancelled" if cancelled else "completed")
    assert projector.finish_open() == []


@pytest.mark.parametrize("structured_output", [{}, False, 0, "", {"answer": 42}])
def test_result_events_preserve_structured_output_and_finish_open_blocks(structured_output):
    projector = ClaudeMessageProjector()
    projector.project(
        AssistantMessage(content=[ToolUseBlock(id="tool", name="python", input={})], model="test", uuid="assistant")
    )
    result = ResultMessage(
        subtype="success",
        duration_ms=1,
        duration_api_ms=1,
        is_error=False,
        num_turns=1,
        session_id="actual-session",
        result="fallback",
        structured_output=structured_output,
        terminal_reason="completed",
    )
    message, response = projector.events(result, session_id="fallback-session", sequence=2)
    assert (message.session_id, message.message_uuid, message.role, message.sequence) == (
        "actual-session",
        "actual-session:2",
        "system",
        2,
    )
    assert message.presentation[0].payload == {"status": "completed"}
    assert response.success
    assert response.answer == structured_output
    assert response.metadata == asdict(result)
    assert projector.finish_open() == []


@pytest.mark.parametrize("answer", [None, "failed answer"])
def test_failed_results_preserve_errors_and_cancel_open_blocks(answer):
    projector = ClaudeMessageProjector()
    projector.project(
        AssistantMessage(content=[ToolUseBlock(id="tool", name="python", input={})], model="test", uuid="assistant")
    )
    result = ResultMessage(
        subtype="error_during_execution",
        duration_ms=1,
        duration_api_ms=1,
        is_error=True,
        num_turns=1,
        session_id="session",
        result=answer,
        errors=["one", "two"],
        structured_output={"ignored": True},
        terminal_reason="aborted_tools",
    )
    message, response = projector.events(result, session_id="session", sequence=1)
    assert message.presentation[0].payload == {"status": "cancelled"}
    assert not response.success
    assert response.answer == (answer or "one; two")
    assert response.metadata["errors"] == ["one", "two"]


def test_complete_tool_input_sets_running_status_without_a_stream_stop():
    projector = ClaudeMessageProjector()
    stream(
        projector,
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "tool_use", "id": "tool", "name": "python", "input": {}},
        },
    )
    patches = projector.project(
        AssistantMessage(
            content=[ToolUseBlock(id="tool", name="python", input={"code": "1 + 1"})], model="test", uuid="assistant"
        )
    )
    assert len(patches) == 1
    assert patches[0].operation == "replace"
    assert patches[0].payload == {"name": "python", "input": {"code": "1 + 1"}, "text": "", "status": "running"}


def test_history_preserves_user_prompts_thinking_and_orphan_tool_results():
    blocks = ClaudeMessageProjector.history(
        [
            SessionMessage(type="user", uuid="user", session_id="session", message={"content": "hello"}),
            SessionMessage(
                type="assistant",
                uuid="assistant",
                session_id="session",
                message={
                    "content": [
                        {"type": "image", "data": "ignored"},
                        {"type": "thinking", "thinking": "plan"},
                        {"type": "text", "text": "answer"},
                    ]
                },
            ),
            # Pagination may include the result without the original tool call.
            SessionMessage(
                type="user",
                uuid="result",
                session_id="session",
                message={
                    "content": [
                        {"type": "tool_result", "tool_use_id": "orphan", "content": "output"},
                    ]
                },
            ),
            SessionMessage(type="assistant", uuid="ignored", session_id="session", message=None),
        ]
    )
    assert [(block.block_id, block.block_type, block.text, block.role, block.status) for block in blocks] == [
        ("user:0", "text", "hello", "user", "completed"),
        ("assistant:1", "thinking", "plan", "assistant", "completed"),
        ("assistant:2", "text", "answer", "assistant", "completed"),
        ("orphan", "tool", "", "user", "succeeded"),
    ]
    assert ClaudeMessageProjector().project(UserMessage(content="hello")) == []


def test_unknown_stream_events_do_not_create_display_blocks():
    projector = ClaudeMessageProjector()
    assert stream(projector, {"type": "content_block_start", "index": 0, "content_block": {"type": "image"}}) == []
    assert (
        stream(projector, {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "x"}})
        == []
    )
    assert stream(projector, {"type": "message_stop"}) == []
