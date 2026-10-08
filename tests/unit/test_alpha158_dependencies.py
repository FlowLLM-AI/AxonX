"""Plugin requirements must match the implementations imported by this checkout."""

from pathlib import Path
import tomllib

from packaging.requirements import Requirement
import pytest

from axonx._version import VERSION

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("plugin", ["a158", "a158_enhanced"])
def test_plugins_accept_current_framework_version(plugin):
    project = tomllib.loads((ROOT / "plugins" / plugin / "pyproject.toml").read_text())["project"]
    requirements = {item.name: item for item in map(Requirement, project["dependencies"])}
    assert requirements["axonx"].specifier.contains(VERSION)
    if plugin == "a158_enhanced":
        base = tomllib.loads((ROOT / "plugins/a158/pyproject.toml").read_text())["project"]
        assert requirements["axonx-alpha158"].specifier.contains(base["version"])
