"""Task discovery and definition queries share submission resolution."""

from pathlib import Path

import httpx
import pytest
import yaml

from axonx.components.client import HttpClient, RemoteServiceError
from axonx.components.service import HttpService
from axonx.core import Application
from axonx.plugin_kit.models import PluginInfo
from axonx.task.builtins import DemoTask
from axonx.task.catalog import (
    get_task_definition,
    installed_tasks,
    list_installed_task_definitions,
    resolve_task,
    resolver,
)


@pytest.fixture
def plugins(monkeypatch):
    items = [
        PluginInfo(
            distribution="example",
            version="1",
            tasks={"example_task": "axonx.task.builtins.demo:DemoTask"},
        )
    ]
    monkeypatch.setattr(resolver, "list_installed_plugins", lambda: items)
    return items


def test_single_and_list_definitions_match_execution(plugins):
    definitions = list_installed_task_definitions()
    assert [item.name for item in definitions] == sorted(item.name for item in definitions)
    tasks = installed_tasks()
    for definition in definitions:
        assert get_task_definition(definition.name) == definition
        assert resolve_task(definition.name) is tasks[definition.name]
    native = get_task_definition("demo")
    assert native.source == "native"
    assert native.plugin is None
    assert native.input_schema == DemoTask.input_cls.model_json_schema()
    assert native.output_schema == DemoTask.output_cls.model_json_schema()
    plugin = get_task_definition("example_task")
    assert plugin.source == "plugin"
    assert plugin.plugin == "example"
    assert plugin.name == "example_task"


def test_single_query_does_not_load_unrelated_task(plugins):
    plugins.append(
        PluginInfo(
            distribution="broken",
            version="1",
            tasks={"broken_task": "nonexistent_axonx_plugin:Task"},
        )
    )
    assert get_task_definition("example_task").name == "example_task"
    assert get_task_definition("demo").name == "demo"
    assert resolve_task("example_task") is DemoTask
    with pytest.raises(ModuleNotFoundError):
        list_installed_task_definitions()


@pytest.mark.parametrize("query", [get_task_definition, resolve_task])
def test_unknown_registration_has_clear_error(plugins, query):
    with pytest.raises(ValueError, match="Unknown Task: missing.*example_task"):
        query("missing")


@pytest.mark.parametrize("query", [get_task_definition, resolve_task, list_installed_task_definitions, installed_tasks])
def test_native_plugin_name_conflicts_are_rejected(plugins, query):
    plugins.append(
        PluginInfo(
            distribution="collision",
            version="1",
            tasks={"demo": "axonx.task.builtins.demo:DemoTask"},
        )
    )
    with pytest.raises(ValueError, match="Plugin Task names conflict with built-ins: demo"):
        if query in (get_task_definition, resolve_task):
            query("demo")
        else:
            query()


async def test_definition_jobs_over_http(tmp_path, plugins):
    defaults = yaml.safe_load(Path("axonx/config/default.yaml").read_text(encoding="utf-8"))["jobs"]
    app = Application(
        workspace_dir=str(tmp_path),
        enable_logo=False,
        log_to_console=False,
        log_to_file=False,
        jobs={name: defaults[name] for name in ("get_task_definition", "list_installed_task_definitions")},
    )
    server = HttpService(token="secret", web_enabled=False).build_service(app)
    async with (
        server.router.lifespan_context(server),
        HttpClient(token="secret", transport=httpx.ASGITransport(app=server)) as client,
    ):
        response = await client.run_job("get_task_definition", {"task": "example_task"})
        assert response.success is True
        assert response.answer == get_task_definition("example_task").model_dump(mode="json")
        listed = await client.run_job("list_installed_task_definitions")
        assert listed.success is True
        assert response.answer in listed.answer
        for arguments in ({}, {"task": ""}, {"task": "demo", "extra": True}):
            with pytest.raises(RemoteServiceError, match="Invalid arguments"):
                await client.run_job("get_task_definition", arguments)
        invalid = await client.run_job("get_task_definition", {"task": "missing"})
        assert invalid.success is False
        assert "Unknown Task: missing" in str(invalid.answer)
