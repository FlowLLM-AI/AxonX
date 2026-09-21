"""Live Agent terminal protocol test."""

import pytest

if __name__ == "__main__":
    raise SystemExit(pytest.main(["-m", "integration", "-s", "-vv", __file__]))

from ._agent_cli import run_live_cli


@pytest.mark.integration
def test_agent_chat_preserves_raw_sdk_result(live_agent_service) -> None:
    output = run_live_cli(live_agent_service)

    assert "Agent / ResultMessage" in output
    assert '"terminal_reason"' in output
    assert "===== BLOCK: ResultEvent =====" in output
