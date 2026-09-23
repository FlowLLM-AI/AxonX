"""External configuration entry point tests."""

from importlib.metadata import EntryPoint

import pytest

from axonx.config import ConfigResolver


def test_config_entry_points_can_name_files_in_a_package(tmp_path, monkeypatch):
    package = tmp_path / "sample_configs"
    directory = package / "config"
    directory.mkdir(parents=True)
    (package / "__init__.py").write_text(
        "from pathlib import Path\n"
        "def config_path():\n"
        "    return Path(__file__).parent / 'config' / 'a1.yaml'\n",
        encoding="utf-8",
    )
    (directory / "a1.yaml").write_text("source: first\n", encoding="utf-8")
    (directory / "a2.yaml").write_text("source: second\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))

    def entries(group, name):
        target = {
            "alpha158": "sample_configs.config:a1",
            "alpha158_2": "sample_configs.config:a2",
            "legacy": "sample_configs:config_path",
            "missing": "sample_configs.config:absent",
        }.get(name, "sample_configs.config")
        return [EntryPoint(name=name, value=target, group=group)]

    monkeypatch.setattr("axonx.config.resolver.find_entry_points", entries)
    resolver = ConfigResolver(tmp_path / "builtins")

    assert resolver.load("a1") == {"source": "first"}
    assert resolver.load("alpha158") == {"source": "first"}
    assert resolver.resolve(config="alpha158_2", log_config=False) == {
        "source": "second",
    }
    assert resolver.load("legacy") == {"source": "first"}
    with pytest.raises(ValueError, match="did not resolve to a YAML or JSON file"):
        resolver.load("missing")
