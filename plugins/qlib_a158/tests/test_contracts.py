"""Validate shipped plugin registrations, configurations and bilingual CLI examples."""

import re
import shlex
import tomllib
from importlib import metadata
from pathlib import Path

import jsonschema
import pytest
from packaging.requirements import Requirement

from axonx.app.config.loader import ConfigLoader
from axonx.app.config.models import ApplicationConfig
from axonx.cli.parser import parse_command, parse_plugin_arguments
from axonx.plugin.manifest import PluginManifest
from axonx.task.runtime.catalog import TaskCatalog
from axonx.task.runtime.settings import ExecutionSettings

PLUGINS = Path(__file__).resolve().parents[2]
NAMES = ("qlib_a158", "qlib_factor", "qlib_strategy")
FENCES = re.compile(r"^```(?:bash|sh)\n(.*?)^```", re.MULTILINE | re.DOTALL)


def project(name):
    return tomllib.loads((PLUGINS / name / "pyproject.toml").read_text())


def task_catalog():
    registrations = []
    for name in NAMES:
        package = "axonx_" + name
        manifest = PluginManifest.parse((PLUGINS / name / package / "plugin.yaml").read_text(), name)
        registrations.extend((key, value, name) for key, value in manifest.tasks.items())
    return TaskCatalog(registrations)


def test_all_shipped_registrations_resolve_with_current_schemas():
    catalog = task_catalog()
    definitions = catalog.definitions()
    assert len(definitions) == 19  # Three built-ins and sixteen research registrations.
    for definition in definitions:
        jsonschema.Draft202012Validator.check_schema(definition.input_schema)
        jsonschema.Draft202012Validator.check_schema(definition.output_schema)


@pytest.mark.parametrize("name", NAMES)
def test_plugin_dependency_layers_require_current_contracts(name):
    config = project(name)
    requirements = {entry.name: entry for entry in map(Requirement, config["project"]["dependencies"])}
    dependencies = ["axonx"]
    if name != "qlib_a158":
        dependencies.append("axonx-qlib-a158")
    if name == "qlib_strategy":
        dependencies.append("axonx-qlib-factor")
    for dependency in dependencies:
        assert "0.3.0" in requirements[dependency].specifier
        assert "0.2.0" not in requirements[dependency].specifier


@pytest.mark.parametrize("name", ["qlib_a158", "qlib_factor"])
def test_named_plugin_configuration_loads_through_declared_entry_point(monkeypatch, name):
    entry = project(name)["project"]["entry-points"]["axonx.configs"][name]
    entries = metadata.EntryPoints([metadata.EntryPoint(name=name, value=entry, group="axonx.configs")])
    monkeypatch.setattr(metadata, "entry_points", entries.select)
    config = ApplicationConfig.model_validate(ConfigLoader().load(name))
    assert config.service.backend == "http"
    assert {"cli", "get_config", "get_task_def", "status"} <= config.jobs.keys()
    assert config.cron == []


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("readme", ["README.md", "README_ZH.md"])
def test_documented_plugin_commands_match_current_contracts(name, readme):
    catalog = task_catalog()
    jobs = ConfigLoader().load("default")["jobs"]
    commands = 0
    for body in FENCES.findall((PLUGINS / name / readme).read_text()):
        for line in body.replace("\\\n", " ").splitlines():
            if not line.strip().startswith("axonx "):
                continue
            for stage, task_type in [("etl", "etl"), ("train", "train"), ("predict", "predict")]:
                line = line.replace(f"<{stage}_task_id>", f"{task_type}#qlib_a158_{stage}#example")
            command, _ = parse_command(shlex.split(line, comments=True)[1:])
            commands += 1
            if command.action == "plugin":
                parse_plugin_arguments(command.raw_arguments)
            elif command.action == "exec":
                inputs = dict(command.arguments)
                task = catalog.resolve(inputs.pop("task"))
                for key in ExecutionSettings.model_fields:
                    inputs.pop(key, None)
                task.input_cls.model_validate(inputs)
            elif command.action == "app":
                ApplicationConfig.model_validate(
                    {key: value for key, value in command.arguments.items() if key != "config"}
                )
            else:
                assert command.action in jobs
                jsonschema.validate(command.arguments, jobs[command.action].get("parameters", {}))
    assert commands >= 10
