from claude_agent_sdk import (
    AssistantMessage,
    ServerToolResultBlock,
    ServerToolUseBlock,
    SessionMessage,
    StreamEvent,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from axonx.app.components.agent.claude.projector import ClaudeMessageProjector, history_blocks


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
    complete = projector.project(AssistantMessage(content=[TextBlock("hello")], model="test", uuid="message-one"))

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
    finished = projector.project(UserMessage(content=[ToolResultBlock(tool_use_id="tool-one", content="ok")]))

    assert started[0].block_id == "tool-one"
    assert finished[0].block_id == "tool-one"
    assert finished[0].operation == "finish"
    assert finished[0].payload["status"] == "succeeded"


def test_projector_replaces_streamed_tool_input_with_complete_arguments():
    projector = ClaudeMessageProjector()

    def stream(event):
        return projector.project(StreamEvent(uuid="message-one", session_id="session-one", event=event))

    stream(
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "tool_use", "id": "tool-one", "name": "Bash", "input": {}},
        }
    )
    for fragment in ['{"command": "echo ', 'hello"}']:
        patches = stream(
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "input_json_delta", "partial_json": fragment},
            }
        )
        assert patches[0].block_id == "tool-one"
        assert patches[0].delta == fragment
    stopped = stream({"type": "content_block_stop", "index": 0})
    assert stopped[0].payload["status"] == "running"

    complete = projector.project(
        AssistantMessage(
            content=[ToolUseBlock(id="tool-one", name="Bash", input={"command": "echo hello"})],
            model="test",
            uuid="message-one",
        )
    )
    assert len(complete) == 1
    assert complete[0].block_id == "tool-one"
    assert complete[0].operation == "replace"
    assert complete[0].payload == {"name": "Bash", "input": {"command": "echo hello"}, "text": ""}

    result = projector.project(UserMessage(content=[ToolResultBlock(tool_use_id="tool-one", content="hello")]))
    assert result[0].block_id == "tool-one"
    assert result[0].payload["status"] == "succeeded"


def test_history_blocks_include_message_ownership():
    messages = [
        {
            "type": "user",
            "uuid": "user-message",
            "message": {
                "role": "user",
                "content": [{"type": "text", "text": "hello"}],
            },
        },
        {
            "type": "assistant",
            "uuid": "assistant-message",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "hi"}],
            },
        },
    ]

    blocks = history_blocks([SessionMessage(**message, session_id="session") for message in messages])

    assert [(block["role"], block["message_uuid"]) for block in blocks] == [
        ("user", "user-message"),
        ("assistant", "assistant-message"),
    ]


def test_history_blocks_include_string_user_messages():
    blocks = history_blocks(
        [
            SessionMessage(
                type="user",
                uuid="user-message",
                session_id="session",
                message={"role": "user", "content": "original question"},
            )
        ]
    )

    assert blocks == [
        {
            "block_id": "user-message:0",
            "block_type": "text",
            "message_uuid": "user-message",
            "role": "user",
            "status": "completed",
            "text": "original question",
            "payload": {},
        }
    ]


def test_projector_does_not_reuse_indices_from_previous_message():
    projector = ClaudeMessageProjector()
    projector.project(
        StreamEvent(
            uuid="first",
            session_id="session",
            event={"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        )
    )
    projector.project(AssistantMessage(content=[TextBlock("first answer")], model="test", uuid="first"))
    patches = projector.project(AssistantMessage(content=[TextBlock("next answer")], model="test", uuid="second"))
    assert {patch.block_id for patch in patches} == {"second:0"}
    assert [patch.operation for patch in patches] == ["start", "replace", "finish"]


def test_projector_preserves_initial_stream_content():
    patches = ClaudeMessageProjector().project(
        StreamEvent(
            uuid="first",
            session_id="session",
            event={"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": "hello"}},
        )
    )
    assert [patch.operation for patch in patches] == ["start", "append"]
    assert patches[1].delta == "hello"


def test_projector_preserves_server_tool_results_in_assistant_message():
    content = {"type": "web_search_tool_result", "results": [{"title": "result"}]}
    patches = ClaudeMessageProjector().project(
        AssistantMessage(
            content=[
                ServerToolUseBlock(id="search", name="web_search", input={"query": "example"}),
                ServerToolResultBlock(tool_use_id="search", content=content),
            ],
            model="test",
            uuid="message",
        )
    )
    assert [patch.operation for patch in patches] == ["start", "finish"]
    assert patches[-1].payload["result"] == content


def test_history_block_ids_are_stable_across_pagination():
    messages = [
        SessionMessage(type="assistant", uuid=name, session_id="session", message={"content": [{"type": "text", "text": name}]})
        for name in ("first", "second")
    ]
    assert history_blocks(messages)[1] == history_blocks(messages[1:])[0]
