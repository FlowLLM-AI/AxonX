import pytest
from pydantic import ValidationError

from axonx.config import ApplicationConfig, ConfigResolver


def test_remote_config_uses_separate_target_token(monkeypatch):
    monkeypatch.setenv("AXONX_TARGET", "192.0.2.10:1024")
    monkeypatch.setenv("AXONX_SERVICE_TOKEN", "local-secret")
    monkeypatch.setenv("AXONX_TARGET_TOKEN", "target-secret")

    config = ApplicationConfig.model_validate(ConfigResolver().load("remote"))

    assert config.service.token == "local-secret"
    assert len(config.targets) == 1
    assert config.targets[0].address == "http://192.0.2.10:1024"
    assert config.targets[0].token == "target-secret"


def test_target_sync_uses_current_names():
    config = ApplicationConfig.model_validate(
        {
            "targets": [{"address": "192.0.2.10:1024", "token": "secret"}],
            "components": {
                "sync": {
                    "default": {
                        "backend": "local",
                        "target": "192.0.2.10:1024",
                    }
                }
            },
        }
    )
    assert config.targets[0].address == "http://192.0.2.10:1024"
    assert config.targets[0].token == "secret"
    assert config.components["sync"]["default"].model_extra["target"] == "192.0.2.10:1024"


def test_target_sync_accepts_ipv6_address():
    config = ApplicationConfig.model_validate(
        {
            "targets": [{"address": "[0:0:0:0:0:0:0:1]:1024"}],
            "components": {
                "sync": {
                    "default": {
                        "backend": "local",
                        "target": "[::1]:1024",
                    }
                }
            },
        }
    )

    assert config.targets[0].address == "http://[::1]:1024"
    assert config.components["sync"]["default"].model_extra["target"] == "[::1]:1024"


def test_removed_config_names_are_rejected():
    with pytest.raises(ValidationError, match="remote_nodes"):
        ApplicationConfig.model_validate({"remote_nodes": []})
    with pytest.raises(ValidationError, match="allow_management"):
        ApplicationConfig.model_validate({"plugins": {"allow_management": True}})
