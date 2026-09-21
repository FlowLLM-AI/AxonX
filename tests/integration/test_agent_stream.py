"""Live partial-delta Agent presentation test."""

import pytest

if __name__ == "__main__":
    raise SystemExit(pytest.main(["-m", "integration", "-s", "-vv", __file__]))

from ._agent_cli import run_live_cli


@pytest.mark.integration
def test_agent_chat_prints_projected_stream_events(live_agent_service) -> None:
    """Print UI projections without exposing Claude delta parsing to consumers."""
    output = run_live_cli(live_agent_service)

    assert "Agent / text / append" in output
    assert "Agent / tool / start" in output
    assert "Agent / tool / finish" in output
    assert '"session_id"' in output
