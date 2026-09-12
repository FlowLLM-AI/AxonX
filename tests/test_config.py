"""Configuration loading, merging, and validation tests."""

# Tests favor descriptive function names over repeated docstrings.
# pylint: disable=missing-function-docstring

import pytest

from axonx.config import (
    ConfigResolver,
    convert_value,
    deep_merge_config,
    expand_env_vars,
    resolve_app_config,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("null", None),
        ("TRUE", True),
        ("42", 42),
        ("1.5", 1.5),
        ("007", "007"),
        ('[1, "two"]', [1, "two"]),
        ("plain text", "plain text"),
    ],
)
def test_convert_value(raw, expected):
    assert convert_value(raw) == expected


def test_expand_env_vars_recursively_and_convert_values():
    value = {"port": "${PORT}", "nested": ["${ENABLED:-false}"]}

    assert expand_env_vars(value, {"PORT": "8080"}) == {
        "port": 8080,
        "nested": [False],
    }


def test_deep_merge_does_not_mutate_inputs():
    base = {"service": {"host": "localhost", "port": 80}}
    update = {"service": {"port": 8080}}

    assert deep_merge_config(base, update) == {
        "service": {"host": "localhost", "port": 8080},
    }
    assert base["service"]["port"] == 80


def test_resolver_loads_relative_inheritance_and_overrides(tmp_path):
    (tmp_path / "base.yaml").write_text(
        "service:\n  host: localhost\n  port: 80\n",
        encoding="utf-8",
    )
    (tmp_path / "child.yaml").write_text(
        "extends: base.yaml\nservice:\n  port: 8080\n",
        encoding="utf-8",
    )
    resolver = ConfigResolver(tmp_path)

    assert resolver.resolve(
        config="child",
        service={"public": True},
        log_config=False,
    ) == {"service": {"host": "localhost", "port": 8080, "public": True}}


def test_resolver_rejects_circular_inheritance(tmp_path):
    (tmp_path / "a.yaml").write_text("extends: b.yaml\n", encoding="utf-8")
    (tmp_path / "b.yaml").write_text("extends: a.yaml\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Circular config inheritance"):
        ConfigResolver(tmp_path).load("a")


def test_resolver_makes_plugin_paths_relative_to_config(tmp_path):
    (tmp_path / "app.yaml").write_text("plugins: [./plugins/demo]\n")

    config = ConfigResolver(tmp_path).load("app")

    assert config["plugins"] == [str((tmp_path / "plugins/demo").resolve())]


def test_default_config_enables_local_plugin_component():
    config = resolve_app_config(log_config=False)

    assert config["components"]["plugin"]["default"] == {
        "backend": "local",
        "auto_install": True,
        "allow_remote_install": True,
    }
