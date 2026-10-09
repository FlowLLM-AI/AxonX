"""Plugin requirements must match the implementations imported by this checkout."""

from pathlib import Path
import tomllib

from packaging.requirements import Requirement
import pytest

from axonx._version import VERSION

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("plugin", ["qlib_a158", "qlib_factor", "qlib_strategy"])
def test_plugins_accept_current_framework_version(plugin):
    project = tomllib.loads((ROOT / "plugins" / plugin / "pyproject.toml").read_text())["project"]
    requirements = {item.name: item for item in map(Requirement, project["dependencies"])}
    assert requirements["axonx"].specifier.contains(VERSION)
    if plugin == "qlib_factor":
        base = tomllib.loads((ROOT / "plugins/qlib_a158/pyproject.toml").read_text())["project"]
        assert requirements["axonx-qlib-a158"].specifier.contains(base["version"])

    if plugin == "qlib_strategy":
        factor = tomllib.loads((ROOT / "plugins/qlib_factor/pyproject.toml").read_text())["project"]
        assert requirements["axonx-qlib-factor"].specifier.contains(factor["version"])
