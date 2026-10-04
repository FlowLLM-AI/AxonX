"""Built-in workspace configuration and override precedence."""

import pytest

from axonx.config import ApplicationConfig, ConfigResolver


@pytest.mark.parametrize("source", ["default", "remote"])
def test_workspace_defaults_to_axonx(source, monkeypatch):
    monkeypatch.delenv("AXONX_WORKSPACE_DIR", raising=False)
    monkeypatch.setenv("AXONX_TARGET", "192.0.2.10:1024")
    monkeypatch.setenv("AXONX_TARGET_TOKEN", "target-secret")

    config = ApplicationConfig.model_validate(ConfigResolver().load(source))

    assert config.workspace_dir == ".axonx"


@pytest.mark.parametrize("source", ["default", "remote"])
def test_workspace_environment_and_explicit_overrides(source, tmp_path, monkeypatch):
    workspace = str(tmp_path / "research workspace")
    monkeypatch.setenv("AXONX_WORKSPACE_DIR", workspace)
    monkeypatch.setenv("AXONX_TARGET", "192.0.2.10:1024")
    monkeypatch.setenv("AXONX_TARGET_TOKEN", "target-secret")
    resolver = ConfigResolver()

    config = ApplicationConfig.model_validate(resolver.load(source))
    assert config.workspace_dir == workspace

    custom = tmp_path / "app.yaml"
    custom.write_text(f"extends: {source}\nworkspace_dir: ./configured-workspace\n", encoding="utf-8")
    config = ApplicationConfig.model_validate(resolver.load(custom))
    assert config.workspace_dir == "./configured-workspace"

    config = ApplicationConfig.model_validate(
        resolver.resolve(config=str(custom), workspace_dir=str(tmp_path / "override"), log_config=False)
    )
    assert config.workspace_dir == str(tmp_path / "override")
    assert ApplicationConfig().workspace_dir == ".axonx"
