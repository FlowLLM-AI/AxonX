from axonx.config import ApplicationConfig, ConfigResolver


def test_remote_config_uses_service_token_for_remote_node(monkeypatch):
    monkeypatch.setenv("AXONX_REMOTE_HOST_IP", "192.0.2.10")
    monkeypatch.setenv("AXONX_SERVICE_TOKEN", "shared-secret")

    config = ApplicationConfig.model_validate(ConfigResolver().load("remote"))

    assert config.service.token == "shared-secret"
    assert len(config.remote_nodes) == 1
    assert config.remote_nodes[0].address == "192.0.2.10:1024"
    assert config.remote_nodes[0].token == "shared-secret"
