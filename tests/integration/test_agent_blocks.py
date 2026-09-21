"""Live Agent folded-response protocol test."""

import json

import pytest

if __name__ == "__main__":
    raise SystemExit(pytest.main(["-m", "integration", "-s", "-vv", __file__]))

from ._agent_cli import run_live_cli


@pytest.mark.integration
def test_agent_chat_folds_non_stream_response(live_agent_service) -> None:
    output = run_live_cli(live_agent_service, stream=False)
    response = json.loads(output)

    assert response["success"] is True
    assert "AXONX_REACT_DONE" in response["answer"]
    assert response["metadata"]["terminal_reason"] == "completed"
    assert "===== BLOCK:" not in output
