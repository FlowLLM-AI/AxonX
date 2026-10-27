"""Exercise component declarations, backend lookup, and lifecycle failures."""

import asyncio
import importlib
import inspect
from unittest.mock import AsyncMock

import pytest

from axonx.app.components.base import BaseComponent, Component
from axonx.app.components.registry import ProviderRegistry, provider
from axonx.app.components.updater.base import BaseUpdaterComponent
from axonx.app.core.application import Application
from axonx.app.steps.base import BaseStep


@provider("memory")
class Resource(BaseComponent):
    component_type = "resource"


@pytest.mark.parametrize(
    ("domain", "base_name", "implementation_module", "implementation_name"),
    [
        ("agent", "BaseAgentComponent", "claude.backend", "ClaudeAgentComponent"),
        ("cron", "BaseCronComponent", "scheduler", "CronComponent"),
        ("job", "BaseJob", "pipeline", "PipelineJob"),
        ("machine", "BaseMachineComponent", "local", "LocalMachineComponent"),
        ("proxy", "BaseProxyComponent", "http", "HttpProxyComponent"),
        ("service", "BaseService", "http.service", "HttpService"),
        ("sync", "BaseSyncComponent", "local", "LocalSyncComponent"),
        ("task_index", "BaseTaskIndex", "local", "LocalTaskIndex"),
        ("updater", "BaseUpdaterComponent", "local", "LocalUpdaterComponent"),
    ],
)
def test_each_domain_has_an_abstract_component_contract_and_concrete_implementation(
    domain, base_name, implementation_module, implementation_name
):
    package = f"axonx.app.components.{domain}"
    base = getattr(importlib.import_module(f"{package}.base"), base_name)
    implementation = getattr(importlib.import_module(f"{package}.{implementation_module}"), implementation_name)
    assert inspect.isabstract(base)
    assert issubclass(base, BaseComponent)
    assert issubclass(implementation, base)
    assert not inspect.isabstract(implementation)
    assert base.component_type == domain


async def test_update_steps_accept_a_backend_implementing_only_the_updater_contract(tmp_path):
    @provider("alternate_updater")
    class AlternateUpdater(BaseUpdaterComponent):
        async def request(self, mode):
            return {"mode": mode, "component": self.name}

        def status(self, update_id=None):
            return {"update_id": update_id, "component": self.name}

    app = Application(
        providers=(AlternateUpdater,),
        workspace_dir=str(tmp_path),
        log_to_console=False,
        log_to_file=False,
        components={"updater": {"selected": {"backend": "alternate_updater"}}},
        jobs={
            "restart": {"steps": [{"backend": "restart_service_step", "updater": "selected"}]},
            "status": {
                "steps": [{"backend": "get_update_status_step", "updater": "selected"}],
            },
        },
    )
    async with app:
        assert (await app.run_job("restart")).answer == {"mode": "restart", "component": "selected"}
        assert (await app.run_job("status", {"update_id": "example"})).answer == {
            "update_id": "example",
            "component": "selected",
        }


def test_registry_keeps_categories_separate_and_rejects_conflicting_backends():
    @provider("memory")
    class OtherCategory(Resource):
        component_type = "other"

    @provider("memory")
    class ConflictingResource(Resource):
        pass

    registry = ProviderRegistry((Resource, OtherCategory, Resource))
    assert registry.require("resource", "memory", Resource) is Resource
    assert registry.require("other", "memory", Resource) is OtherCategory
    with pytest.raises(ValueError, match="supplied by both"):
        registry.add(ConflictingResource)
    with pytest.raises(ValueError, match="Unknown resource backend"):
        registry.require("resource", "missing", Resource)
    with pytest.raises(TypeError, match="must subclass OtherCategory"):
        registry.require("resource", "memory", OtherCategory)


def test_subclasses_must_declare_their_own_provider_name():
    class UndeclaredResource(Resource):
        pass

    with pytest.raises(TypeError, match="must be decorated"):
        ProviderRegistry((UndeclaredResource,))
    with pytest.raises(TypeError, match="already declares"):
        provider("different")(Resource)
    assert ProviderRegistry((Resource,)).require("resource", "memory", Resource) is Resource


@pytest.mark.parametrize("name", ["", "  ", None, 1])
def test_provider_names_must_be_nonempty_strings(name):
    with pytest.raises(ValueError, match="Provider name"):
        provider(name)


@pytest.mark.parametrize("implementation", [object, object(), Resource()])
def test_registry_rejects_noncomponent_providers(implementation):
    with pytest.raises(TypeError, match="must subclass Component"):
        ProviderRegistry((implementation,))


@pytest.mark.parametrize("category", ["", "  ", None, 1])
def test_provider_categories_must_be_nonempty_strings(category):
    @provider("invalid")
    class InvalidCategory(Component):
        component_type = category

    with pytest.raises(TypeError, match="non-empty component_type"):
        ProviderRegistry((InvalidCategory,))


def test_omitted_optional_dependencies_still_reserve_their_attribute():
    resource = Resource()
    resource.depend("optional", None, Resource, required=False)
    assert resource.optional is None
    with pytest.raises(ValueError, match="already declared"):
        resource.depend("optional", "default", Resource)


@pytest.mark.parametrize("name", ["", "  ", 1])
def test_dependency_names_are_validated_even_when_optional(name):
    with pytest.raises(ValueError, match="Dependency name"):
        Resource().depend("resource", name, Resource, required=False)


@pytest.mark.parametrize("base", [object, Component, Resource()])
def test_dependencies_must_target_managed_components(base):
    with pytest.raises(TypeError, match="must subclass BaseComponent"):
        Resource().depend("resource", "default", base)


def test_dependency_declarations_reject_invalid_attributes_and_missing_targets():
    resource = Resource()
    with pytest.raises(ValueError, match="Invalid dependency attribute"):
        resource.depend("invalid-name", "default", Resource)
    with pytest.raises(ValueError, match="requires a component name"):
        resource.depend("resource", None, Resource)
    with pytest.raises(TypeError, match="non-empty component_type"):
        resource.depend("resource", "default", BaseComponent)


async def test_steps_resolve_named_components_from_their_base_type(tmp_path):
    @provider("read_resource")
    class ReadResource(BaseStep):
        async def execute(self):
            resource = self.component(Resource)
            self.response.answer = resource.name

    app = Application(
        providers=(Resource, ReadResource),
        workspace_dir=str(tmp_path),
        log_to_console=False,
        log_to_file=False,
        components={"resource": {name: {"backend": "memory"} for name in ("default", "selected")}},
        jobs={
            "default": {"steps": [{"backend": "read_resource"}]},
            "selected": {"steps": [{"backend": "read_resource", "resource": "selected"}]},
            "missing": {"steps": [{"backend": "read_resource", "resource": "missing"}]},
        },
    )
    async with app:
        assert (await app.run_job("default")).answer == "default"
        assert (await app.run_job("selected")).answer == "selected"
        response = await app.run_job("missing")
        assert not response.success
        assert "Unknown resource component" in response.answer


@pytest.mark.parametrize("error_type", [RuntimeError, asyncio.CancelledError])
async def test_startup_preserves_its_own_rollback_failure_and_can_be_retried(error_type, monkeypatch):
    resource = Resource()
    start_error, cleanup_error = error_type("start"), RuntimeError("cleanup")
    start, close = AsyncMock(side_effect=start_error), AsyncMock(side_effect=cleanup_error)
    monkeypatch.setattr(resource, "_start", start)
    monkeypatch.setattr(resource, "_close", close)
    with pytest.raises(BaseExceptionGroup) as failure:
        await resource.start()
    assert failure.value.exceptions == (start_error, cleanup_error)
    assert not resource.is_started

    start.side_effect = None
    close.side_effect = None
    await asyncio.gather(resource.start(), resource.start())
    assert resource.is_started
    assert start.await_count == 2
    await asyncio.gather(resource.close(), resource.close())
    assert not resource.is_started
    assert close.await_count == 2
