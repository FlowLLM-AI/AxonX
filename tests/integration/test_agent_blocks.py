"""Live complete-block Agent presentation test."""

import pytest

if __name__ == "__main__":
    raise SystemExit(pytest.main(["-m", "integration", "-s", "-vv", __file__]))

from ._agent_cli import run_live_cli


@pytest.mark.integration
def test_agent_ask_prints_complete_labelled_blocks(live_agent_service) -> None:
    """Print complete reasoning, text, tool-call and tool-result blocks."""
    output = run_live_cli(live_agent_service, "agent_ask")

    assert "Backend / StreamEvent" not in output
    assert "Backend / AssistantMessage / TextBlock" in output
    assert "Backend / AssistantMessage / ToolUseBlock" in output
    assert "Backend / UserMessage / ToolResultBlock" in output
    assert output.count('"name": "mcp__axonx__version"') == 2
    assert output.count('"name": "mcp__axonx__shell"') == 1
