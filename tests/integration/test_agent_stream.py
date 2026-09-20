"""Live partial-delta Agent presentation test."""

import pytest

if __name__ == "__main__":
    raise SystemExit(pytest.main(["-m", "integration", "-s", "-vv", __file__]))

from ._agent_cli import run_live_cli


@pytest.mark.integration
def test_agent_chat_prints_all_labelled_stream_events(live_agent_service) -> None:
    """Print every partial reasoning, text and tool-input event immediately."""
    output = run_live_cli(live_agent_service, "agent_chat")

    assert "Backend / StreamEvent / content_block_delta / text_delta" in output
    assert "Backend / StreamEvent / content_block_delta / input_json_delta" in output
    assert "Backend / AssistantMessage / ToolUseBlock" in output
    assert "Backend / UserMessage / ToolResultBlock" in output
    assert output.count('"name": "mcp__axonx__version"') >= 2
    assert output.count('"name": "mcp__axonx__shell"') >= 1
