import pytest

from axonx.app.components.service import HttpService
from axonx.config import ConfigResolver


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_cleanup_deadline_must_be_finite_and_positive(timeout):
    with pytest.raises(ValueError, match="cleanup_timeout"):
        HttpService(cleanup_timeout=timeout)


@pytest.mark.parametrize("source", ["default", "remote"])
def test_cleanup_timeout_configuration_and_environment_override(tmp_path, monkeypatch, source):
    monkeypatch.delenv("AXONX_SERVICE_CLEANUP_TIMEOUT", raising=False)
    monkeypatch.setenv("AXONX_TARGET", "192.0.2.10:1024")
    monkeypatch.setenv("AXONX_TARGET_TOKEN", "test-token")
    resolver = ConfigResolver()
    assert resolver.load(source)["service"]["cleanup_timeout"] == 15
    monkeypatch.setenv("AXONX_SERVICE_CLEANUP_TIMEOUT", "0.5")
    assert resolver.load(source)["service"]["cleanup_timeout"] == 0.5
    config = tmp_path / "custom.yaml"
    config.write_text(f"extends: {source}\nservice:\n  cleanup_timeout: 3\n")
    assert resolver.load(config)["service"]["cleanup_timeout"] == 3
