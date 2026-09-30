from axonx.config import ApplicationConfig, ConfigResolver


def test_remote_config_uses_service_token_for_target(monkeypatch):
    monkeypatch.setenv("AXONX_TARGET", "192.0.2.10:1024")
    monkeypatch.setenv("AXONX_SERVICE_TOKEN", "shared-secret")

    config = ApplicationConfig.model_validate(ConfigResolver().load("remote"))

    assert config.service.token == "shared-secret"
    assert len(config.targets) == 1
    assert config.targets[0].address == "http://192.0.2.10:1024"
    assert config.targets[0].token == "shared-secret"


def test_legacy_remote_node_and_plugin_setting_are_migrated():
    config = ApplicationConfig.model_validate(
        {
            "targets": [],
            "remote_nodes": [
                {"host_ip": "192.0.2.10", "host_port": 1024, "token": "secret"}
            ],
            "plugins": {
                "allow_management": False,
                "allow_remote_management": True,
            },
            "components": {
                "sync": {
                    "default": {
                        "backend": "local",
                        "remote_ip": "192.0.2.10",
                    }
                }
            },
        }
    )
    assert config.targets[0].address == "http://192.0.2.10:1024"
    assert config.targets[0].token == "secret"
    assert config.plugins.allow_management is True
    assert config.components["sync"]["default"].model_extra["target"] == "192.0.2.10:1024"
    assert "remote_ip" not in config.components["sync"]["default"].model_extra


def test_legacy_sync_matches_equivalent_ipv6_spelling():
    config = ApplicationConfig.model_validate(
        {
            "remote_nodes": [
                {"host_ip": "::1", "host_port": 1024},
            ],
            "components": {
                "sync": {
                    "default": {
                        "backend": "local",
                        "remote_ip": "0:0:0:0:0:0:0:1",
                    }
                }
            },
        }
    )

    assert config.targets[0].address == "http://[::1]:1024"
    assert config.components["sync"]["default"].model_extra["target"] == "[::1]:1024"
