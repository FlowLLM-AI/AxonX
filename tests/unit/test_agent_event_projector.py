from claude_agent_sdk import (
    AssistantMessage,
    StreamEvent,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from axonx.components.agent.claude.projector import ClaudeMessageProjector


def test_projector_coalesces_text_delta_with_complete_message():
    projector = ClaudeMessageProjector()
    start = projector.project(
        StreamEvent(
            uuid="message-one",
            session_id="session-one",
            event={
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            },
        )
    )
    append = projector.project(
        StreamEvent(
            uuid="message-one",
            session_id="session-one",
            event={
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": "hello"},
            },
        )
    )
    complete = projector.project(
        AssistantMessage(content=[TextBlock("hello")], model="test", uuid="message-one")
    )

    assert [item.operation for item in start] == ["start"]
    assert append[0].delta == "hello"
    assert [item.operation for item in complete] == ["finish"]


def test_projector_pairs_tool_result_with_tool_use_id():
    projector = ClaudeMessageProjector()
    started = projector.project(
        AssistantMessage(
            content=[ToolUseBlock(id="tool-one", name="status", input={"id": 1})],
            model="test",
            uuid="message-one",
        )
    )
    finished = projector.project(
        UserMessage(
            content=[ToolResultBlock(tool_use_id="tool-one", content="ok")]
        )
    )

    assert started[0].block_id == "tool-one"
    assert finished[0].block_id == "tool-one"
    assert finished[0].operation == "finish"
    assert finished[0].payload["status"] == "succeeded"
