"""Exercise application assembly, dependency injection, lifecycle, and dispatch."""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from axonx.app.components.base import BaseComponent
from axonx.app.components.job.base import BaseJob
from axonx.app.components.registry import provider
from axonx.app.components.service.base import BaseService
from axonx.app.core.application import Application
from axonx.app.core.banner import print_logo
from axonx.client.events import ResultEvent
from axonx.client.models import JobResponse


@pytest.fixture
def runtime(tmp_path):
    events = []

    class RecordingLifecycle:
        def __init__(self, needs=None, optional=None, fail_start=False, fail_close=False, **kwargs):
            super().__init__(**kwargs)
            self.fail_start = fail_start
            self.fail_close = fail_close
            self.components_view = self.app_context.components
            for required, dependencies in ((True, needs), (False, optional)):
                for kind, name in (dependencies or {}).items():
                    self.depend(kind, name, bases[kind], required=required)

        async def _start(self):
            events.append(("start", self.name))
            for dependency in self.dependencies:
                target = getattr(self, dependency.attribute)
                assert target is None or target.is_started
            if self.fail_start:
                raise RuntimeError(f"start:{self.name}")

        async def _close(self):
            events.append(("close", self.name))
            if self.fail_close:
                raise RuntimeError(f"close:{self.name}")

    @provider("test_resource")
    class Resource(RecordingLifecycle, BaseComponent):
        component_type = "resource"

    @provider("test_job")
    class Job(RecordingLifecycle, BaseJob):
        def _injected_parameters(self):
            return {"depth": {"type": "integer", "minimum": 0}}

        async def stream(self, arguments, system):
            yield ResultEvent(answer={"arguments": dict(arguments), "system": dict(system)})

    @provider("test_service")
    class Service(RecordingLifecycle, BaseService):
        def build_service(self, app):
            return None

        def run_app(self, app):
            return None

    @provider("other_resource")
    class OtherResource(BaseComponent):
        component_type = "resource"

    bases = {"resource": Resource, "job": Job, "service": Service}

    def make(**config):
        return Application(
            providers=(Resource, Job, Service, OtherResource),
            workspace_dir=str(tmp_path),
            log_to_console=False,
            log_to_file=False,
            **config,
        )

    return make, events


async def test_all_managed_objects_follow_dependencies_and_restart_idempotently(runtime):
    make, events = runtime
    app = make(
        components={
            "resource": {
                "leaf": {"backend": "test_resource", "needs": {"job": "work"}},
                "root": {"backend": "test_resource"},
                "independent": {"backend": "test_resource"},
            }
        },
        jobs={"work": {"backend": "test_job", "needs": {"resource": "root"}}},
        service={"backend": "test_service", "needs": {"job": "work"}},
    )
    resources = app.context.components["resource"]
    assert resources["leaf"].job is app.context.jobs["work"]
    assert app.context.jobs["work"].resource is resources["root"]
    assert app.context.service.job is app.context.jobs["work"]
    assert resources["leaf"].components_view is app.context.components
    expected = ["root", "independent", "work", "leaf", "service"]

    for _ in range(2):
        events.clear()
        await asyncio.gather(app.start(), app.start())
        assert app.is_started
        assert not app.context.metadata.get("stopping")
        assert events == [("start", name) for name in expected]
        await asyncio.gather(app.close(), app.close())
        assert not app.is_started
        assert events == [("start", name) for name in expected] + [("close", name) for name in reversed(expected)]


async def test_optional_dependencies_are_injected_and_ready_nodes_keep_configuration_order(runtime):
    make, events = runtime
    app = make(
        components={
            "resource": {
                "leaf": {"backend": "test_resource", "optional": {"resource": "root", "job": "missing"}},
                "root": {"backend": "test_resource"},
                "independent": {"backend": "test_resource"},
            }
        }
    )
    leaf = app.context.components["resource"]["leaf"]
    assert leaf.resource is app.context.components["resource"]["root"]
    assert leaf.job is None
    async with app:
        assert events == [("start", "root"), ("start", "leaf"), ("start", "independent")]


@pytest.mark.parametrize(
    ("config", "error", "message"),
    [
        ({"jobs": {"work": {"backend": "test_job", "needs": {"resource": "missing"}}}}, ValueError, "missing"),
        ({"service": {"backend": "test_service", "needs": {"job": "missing"}}}, ValueError, "missing"),
        (
            {
                "components": {"resource": {"root": {"backend": "other_resource"}}},
                "jobs": {"work": {"backend": "test_job", "optional": {"resource": "root"}}},
            },
            TypeError,
            "must be a Resource",
        ),
        (
            {
                "components": {"resource": {"root": {"backend": "test_resource", "needs": {"job": "work"}}}},
                "jobs": {"work": {"backend": "test_job", "needs": {"service": "service"}}},
                "service": {"backend": "test_service", "needs": {"resource": "root"}},
            },
            ValueError,
            "circular dependencies",
        ),
    ],
)
def test_invalid_dependency_graphs_fail_before_starting(runtime, config, error, message):
    make, events = runtime
    with pytest.raises(error, match=message):
        make(**config)
    assert not events


@pytest.mark.parametrize("category", ["job", "service", "step"])
def test_reserved_component_categories_have_one_configuration_entrypoint(runtime, category):
    make, _ = runtime
    with pytest.raises(ValueError, match="Configure"):
        make(components={category: {}})


def test_scheduled_cron_does_not_overwrite_a_configured_component(runtime):
    make, _ = runtime
    with pytest.raises(ValueError, match="top-level cron"):
        make(
            launch_scheduled=AsyncMock(),
            cron=[{"expression": "* * * * *", "command": "worker"}],
            components={"cron": {"default": {"backend": "custom"}}},
        )


def test_context_views_and_provider_registries_are_sealed_and_isolated(runtime):
    make, _ = runtime
    app = make(components={"resource": {"root": {"backend": "test_resource"}}})
    other = make()
    assert not other.context.components
    assert other.context.registry is not app.context.registry
    assert app.context.registry.frozen
    with pytest.raises(TypeError):
        app.context.components["resource"]["other"] = object()
    with pytest.raises(TypeError):
        app.context.components["other"] = {}
    with pytest.raises(TypeError):
        app.context.jobs["other"] = object()
    with pytest.raises(RuntimeError, match="already finalized"):
        app.context.finalize({}, {}, None)
    with pytest.raises(RuntimeError, match="frozen"):
        app.context.registry.add(type(app.context.components["resource"]["root"]))


async def test_startup_failure_preserves_rollback_errors_and_stops_every_started_object(runtime):
    make, events = runtime
    app = make(
        components={"resource": {"root": {"backend": "test_resource", "fail_close": True}}},
        jobs={"work": {"backend": "test_job", "fail_start": True}},
        service={"backend": "test_service"},
    )
    with pytest.raises(ExceptionGroup) as failure:
        await app.start()
    assert [str(error) for error in failure.value.exceptions] == ["start:work", "close:root"]
    assert events == [("start", "root"), ("start", "work"), ("close", "work"), ("close", "root")]
    assert app.context.metadata["stopping"]
    assert not app.is_started
    assert not app.context.components["resource"]["root"].is_started
    app.context.components["resource"]["root"].fail_close = False
    app.context.jobs["work"].fail_start = False
    async with app:
        assert app.is_started


async def test_startup_cancellation_rolls_back_jobs_and_components(runtime, monkeypatch):
    make, events = runtime
    app = make(
        components={"resource": {"root": {"backend": "test_resource"}}},
        jobs={"work": {"backend": "test_job"}},
    )
    entered = asyncio.Event()

    async def blocked_start():
        events.append(("start", "work"))
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(app.context.jobs["work"], "_start", blocked_start)
    start = asyncio.create_task(app.start())
    await asyncio.wait_for(entered.wait(), 1)
    start.cancel()
    with pytest.raises(asyncio.CancelledError):
        await start
    assert events[-2:] == [("close", "work"), ("close", "root")]
    assert not app.is_started
    assert app.context.metadata["stopping"]


async def test_close_continues_after_failures_and_reports_them_in_reverse_order(runtime):
    make, events = runtime
    app = make(
        components={"resource": {"root": {"backend": "test_resource", "fail_close": True}}},
        jobs={"work": {"backend": "test_job"}},
        service={"backend": "test_service", "fail_close": True},
    )
    await app.start()
    with pytest.raises(ExceptionGroup) as failure:
        await app.close()
    assert [str(error) for error in failure.value.exceptions] == ["close:service", "close:root"]
    assert events[-3:] == [("close", "service"), ("close", "work"), ("close", "root")]
    assert not app.is_started
    assert not app.context.service.is_started
    await app.close()


async def test_shutdown_rejects_new_calls_before_cleanup_finishes(runtime, monkeypatch):
    make, _ = runtime
    app = make(jobs={"work": {"backend": "test_job"}}, service={"backend": "test_service"})
    entered, release = asyncio.Event(), asyncio.Event()

    async def blocked_close():
        entered.set()
        await release.wait()

    monkeypatch.setattr(app.context.service, "_close", blocked_close)
    await app.start()
    app.request_shutdown()
    with pytest.raises(RuntimeError, match="not running"):
        await app.run_job("work")
    close = asyncio.create_task(app.close())
    try:
        await asyncio.wait_for(entered.wait(), 1)
        assert not app.is_started
        with pytest.raises(RuntimeError, match="not running"):
            app.stream_job("work")
    finally:
        release.set()
        await close


async def test_dispatch_validates_business_and_system_arguments_for_both_call_modes(runtime):
    make, _ = runtime
    app = make(
        jobs={
            "work": {
                "backend": "test_job",
                "parameters": {"properties": {"value": {"type": "integer"}}, "required": ["value"]},
            },
            "ordinary": {"backend": "test_job", "enable_stream": False},
        }
    )
    async with app:
        dispatcher = app.context.dispatcher
        arguments, system = {"value": 3}, {"depth": 1}
        response = await dispatcher.run("work", arguments, system=system)
        stream = dispatcher.stream("work", arguments, system=system)
        assert [event.response() async for event in stream] == [response]
        assert response.answer == {"arguments": arguments, "system": system}
        assert (arguments, system) == ({"value": 3}, {"depth": 1})
        assert (await app.run_job("ordinary")).success
        for name, public, internal, message in (
            ("missing", {}, {}, "Unknown job"),
            ("work", {}, {}, "Invalid arguments"),
            ("work", {"value": 3, "depth": 1}, {}, "System-owned arguments"),
            ("work", {"value": 3}, {"depth": -1}, "Invalid system arguments"),
        ):
            with pytest.raises(ValueError, match=message):
                dispatcher.stream(name, public, system=internal)
            with pytest.raises(ValueError, match=message):
                await dispatcher.run(name, public, system=internal)
        with pytest.raises(ValueError, match="does not support streaming"):
            app.stream_job("ordinary")


async def test_remote_dispatch_uses_configured_credentials_without_requiring_a_local_job(runtime, monkeypatch):
    make, _ = runtime
    app = make(targets=[{"address": "remote:1024", "token": "secret"}])
    response = JobResponse(answer="remote")
    remote_run = AsyncMock(return_value=response)
    remote_stream = Mock(return_value=object())
    monkeypatch.setattr("axonx.app.core.dispatch.client.run_remote_job", remote_run)
    monkeypatch.setattr("axonx.app.core.dispatch.client.stream_remote_job", remote_stream)
    async with app:
        assert await app.run_job("remote_only", {"value": 3}, target="remote:1024") is response
        assert app.stream_job("remote_only", {"value": 3}, target="remote:1024") is remote_stream.return_value
        expected = {"target": "http://remote:1024", "token": "secret"}
        remote_run.assert_awaited_once_with("remote_only", {"value": 3}, **expected)
        remote_stream.assert_called_once_with("remote_only", {"value": 3}, **expected)
        for system, target, message in (
            ({"depth": 1}, "remote:1024", "System arguments"),
            ({}, "unknown:1024", "not configured"),
        ):
            with pytest.raises(ValueError, match=message):
                app.context.dispatcher.stream("remote_only", system=system, target=target)
            with pytest.raises(ValueError, match=message):
                await app.context.dispatcher.run("remote_only", system=system, target=target)


async def test_maintenance_admission_is_shared_by_ordinary_and_streaming_calls(runtime):
    make, _ = runtime
    app = make(jobs={name: {"backend": "test_job"} for name in ("work", "version", "get_update_status", "cli")})
    async with app:
        app.context.metadata["maintenance"] = True
        for name, arguments in (("version", {}), ("get_update_status", {}), ("cli", {"argv": ["version"]})):
            response = await app.run_job(name, arguments)
            assert [event.response() async for event in app.stream_job(name, arguments)] == [response]
        for name, arguments in (("work", {}), ("cli", {"argv": ["exec"]})):
            with pytest.raises(ValueError, match="maintenance"):
                await app.run_job(name, arguments)
            with pytest.raises(ValueError, match="maintenance"):
                app.stream_job(name, arguments)


def test_banner_formats_ipv6_endpoints(runtime, capsys):
    make, _ = runtime
    app = make(service={"backend": "http", "host": "::1"})
    print_logo(app.app_config, app.context.service)
    assert "http://[::1]:1024" in capsys.readouterr().out
