"""Application configuration sources, inheritance and validation contracts."""

import json
import sys
from copy import deepcopy
from importlib import metadata

import pytest
import yaml

from axonx.app.config.loader import ConfigLoader, deep_merge_config
from axonx.app.config.models import ApplicationConfig, JobConfig


@pytest.fixture
def installed_configs(tmp_path, monkeypatch):
    package = tmp_path / "config_provider"
    package.mkdir()
    (package / "__init__.py").write_text("def preset():\n    raise AssertionError('Called a config factory')\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    entries = []
    monkeypatch.setattr(metadata, "entry_points", lambda **filters: metadata.EntryPoints(entries).select(**filters))
    yield package, entries
    sys.modules.pop("config_provider.__init__", None)
    sys.modules.pop("config_provider", None)


def test_resolve_accepts_paths_and_applies_explicit_overrides(tmp_path):
    path = tmp_path / "default.yaml"
    path.write_text("nested: {keep: true, replace: 1}\nitems: [1, 2]\n")
    loader = ConfigLoader(tmp_path)
    assert loader.resolve(log_config=False) == {"nested": {"keep": True, "replace": 1}, "items": [1, 2]}
    assert loader.resolve(config=path, log_config=False, nested={"replace": None}, items=[]) == {
        "nested": {"keep": True, "replace": None},
        "items": [],
    }
    path.write_text("nested: {fresh: true}\n")
    assert loader.resolve(config=str(path), log_config=False) == {"nested": {"fresh": True}}


def test_inheritance_preserves_order_and_prefers_parent_relative_paths(tmp_path, monkeypatch):
    child_dir = tmp_path / "child"
    child_dir.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AXONX_TEST_PARENT", "base.yml")
    monkeypatch.setenv("AXONX_TEST_VALUE", "42")
    (tmp_path / "base.yml").write_text("wrong: true\n")
    (child_dir / "base.yml").write_text("nested: {keep: true, value: 1}\nitems: [1, 2]\n")
    (child_dir / "second.json").write_text(json.dumps({"extends": "base.yml", "nested": {"value": 2}}))
    (child_dir / "app.yaml").write_text(
        "extends: [\"${AXONX_TEST_PARENT}\", second.json]\nnested: {final: '${AXONX_TEST_VALUE}'}\nitems: []\n"
    )
    assert ConfigLoader().load(child_dir / "app.yaml") == {
        "nested": {"keep": True, "value": 2, "final": 42},
        "items": [],
    }


def test_merge_replaces_non_mappings_without_mutating_inputs():
    base = {"nested": {"keep": [1], "value": 1}, "replace": {"old": True}}
    update = {"nested": {"value": 2}, "replace": [], "empty": None}
    original_base, original_update = deepcopy(base), deepcopy(update)
    assert deep_merge_config(base, update) == {
        "nested": {"keep": [1], "value": 2},
        "replace": [],
        "empty": None,
    }
    assert base == original_base
    assert update == original_update


def test_names_prefer_yaml_then_yml_then_json_and_explicit_paths_are_exact(tmp_path, installed_configs):
    for index, extension in enumerate((".yaml", ".yml", ".json")):
        (tmp_path / f"preset{extension}").write_text(json.dumps({"value": index}))
    loader = ConfigLoader(tmp_path)
    assert loader.load("preset") == {"value": 0}
    assert loader.load("preset.yml") == {"value": 1}
    assert loader.load(tmp_path / "preset.json") == {"value": 2}


@pytest.mark.parametrize("entry_value", ["config_provider:preset", "config_provider"])
def test_installed_entries_load_package_files_and_inherit_bundled_config(installed_configs, entry_value):
    package, entries = installed_configs
    entries.append(metadata.EntryPoint(name="preset", value=entry_value, group="axonx.configs"))
    (package / "preset.yaml").write_text("extends: default\nworkspace_dir: plugin-workspace\n")
    config = ApplicationConfig(**ConfigLoader().resolve(config="preset", log_config=False))
    assert config.workspace_dir == "plugin-workspace"
    assert config.jobs["get_config"].steps[0].backend == "get_config_step"


@pytest.mark.parametrize("builtin", [True, False])
def test_ambiguous_named_configs_fail_before_importing_providers(tmp_path, installed_configs, builtin):
    _, entries = installed_configs
    entry = metadata.EntryPoint(name="preset", value="missing_package:preset", group="axonx.configs")
    entries.append(entry)
    if builtin:
        (tmp_path / "preset.yaml").write_text("value: builtin\n")
    else:
        entries.append(entry)
    error = "both AxonX" if builtin else "multiple installed providers"
    loader = ConfigLoader(tmp_path)
    with pytest.raises(ValueError, match=error):
        loader.load("preset")
    explicit = tmp_path / "explicit.yaml"
    explicit.write_text("value: explicit\n")
    assert loader.load(explicit) == {"value": "explicit"}


@pytest.mark.parametrize("entry_value", ["config_provider:preset", "config_provider.__init__:preset"])
def test_invalid_installed_resources_fail_clearly(installed_configs, entry_value):
    _, entries = installed_configs
    entries.append(metadata.EntryPoint(name="preset", value=entry_value, group="axonx.configs"))
    with pytest.raises(ValueError, match="Config entry point 'preset'"):
        ConfigLoader().load("preset")


def test_inheritance_cycles_are_detected_through_symlinks(tmp_path):
    (tmp_path / "first.yaml").write_text("extends: second.yml\n")
    (tmp_path / "second.yml").write_text("extends: alias.yaml\n")
    (tmp_path / "alias.yaml").symlink_to(tmp_path / "first.yaml")
    with pytest.raises(ValueError, match=r"Circular config inheritance: .*first.yaml.*second.yml.*first.yaml"):
        ConfigLoader(tmp_path).load("first")


@pytest.mark.parametrize("parents", [None, False, 0, 1, {}, {"base": "default"}, "", [" "], [1]])
def test_invalid_inheritance_declarations_are_rejected(tmp_path, parents):
    path = tmp_path / "invalid.yaml"
    path.write_text(yaml.safe_dump({"extends": parents}))
    with pytest.raises(ValueError, match="Config 'extends'"):
        ConfigLoader().load(path)


@pytest.mark.parametrize("text", ["[]", "1", "true", "hello"])
def test_config_root_must_be_a_mapping(tmp_path, text):
    path = tmp_path / "invalid.yaml"
    path.write_text(text)
    with pytest.raises(ValueError, match="Config root must be a mapping"):
        ConfigLoader().load(path)


def test_empty_files_and_missing_sources(tmp_path):
    path = tmp_path / "empty.yaml"
    path.touch()
    loader = ConfigLoader(tmp_path)
    assert loader.load(path) == {}
    with pytest.raises(FileNotFoundError, match="missing"):
        loader.load("missing")
    with pytest.raises(FileNotFoundError, match="default"):
        loader.resolve(log_config=False)


@pytest.mark.parametrize("source", ["", " ", False, 0, {}, []])
def test_invalid_config_sources_are_rejected(source):
    with pytest.raises(ValueError, match="Config source"):
        ConfigLoader().resolve(config=source, log_config=False)


def test_models_preserve_backend_options_and_reject_duplicate_targets():
    job = JobConfig(steps=[{"backend": "custom", "option": 42}], event_buffer_size=8)
    assert job.backend == "pipeline"
    assert job.model_dump()["event_buffer_size"] == 8
    assert job.steps[0].model_dump() == {"backend": "custom", "option": 42}
    with pytest.raises(ValueError, match="parameters must describe a JSON object"):
        JobConfig(parameters={"type": "array"})
    with pytest.raises(ValueError, match="Target addresses must be unique"):
        ApplicationConfig(targets=[{"address": "host:1024"}, {"address": "http://host:1024/"}])
    config = ApplicationConfig(targets=[{"address": "host:1024", "token": "secret"}])
    assert config.resolve_target("http://host:1024/").token == "secret"
    with pytest.raises(ValueError, match="not configured"):
        config.resolve_target("other:1024")
