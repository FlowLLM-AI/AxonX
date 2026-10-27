"""Task registration snapshots, lazy resolution and definition queries."""

from types import SimpleNamespace

import pytest

from axonx.task.builtins.demo import DemoTask
from axonx.task.runtime import catalog


def test_catalog_snapshots_registrations_loads_on_demand_and_keeps_ownership(monkeypatch):
    imports = []
    registrations = [("research", "package:Task", "example"), ("unrelated", "missing:Task", "example")]
    monkeypatch.setattr(
        catalog, "import_module", lambda module: imports.append(module) or SimpleNamespace(Task=DemoTask)
    )
    tasks = catalog.TaskCatalog(registrations)
    registrations.clear()
    assert not imports
    assert tasks.resolve("research") is DemoTask
    assert tasks.resolve("research") is DemoTask
    assert tasks.definition("research").plugin == "example"
    assert imports == ["package"]
    with pytest.raises(ValueError, match="Unknown Task: absent.*Available:"):
        tasks.resolve("absent")


def test_catalog_omits_schema_generation_when_listing_task_info(monkeypatch):
    monkeypatch.setattr(catalog, "BUILTIN_TASKS", {"demo": DemoTask})
    monkeypatch.setattr(DemoTask.input_cls, "model_json_schema", lambda: pytest.fail("Generated an input schema"))
    monkeypatch.setattr(DemoTask.output_cls, "model_json_schema", lambda: pytest.fail("Generated an output schema"))
    assert catalog.TaskCatalog().definitions(include_schemas=False)[0].name == "demo"


def test_catalog_rejects_duplicate_plugin_tasks():
    registrations = [("same", "missing:Task", name) for name in ("one", "two")]
    with pytest.raises(ValueError, match="plugins 'one' and 'two'"):
        catalog.TaskCatalog(registrations)


@pytest.mark.parametrize("target", ["invalid", ":Task", "package:", "builtins:dict"])
def test_catalog_rejects_invalid_task_targets(target):
    with pytest.raises((TypeError, ValueError), match="Task target"):
        catalog.TaskCatalog([("research", target, "example")]).resolve("research")


def test_catalog_only_loads_the_requested_task():
    tasks = catalog.TaskCatalog([("unrelated", "missing_package:Task", "example")])
    assert tasks.definition("demo").name == "demo"
    with pytest.raises(ModuleNotFoundError):
        tasks.resolve("unrelated")


def test_catalog_rejects_plugin_names_that_shadow_builtins():
    with pytest.raises(ValueError, match="conflict"):
        catalog.TaskCatalog([("demo", "missing_package:Task", "example")])
