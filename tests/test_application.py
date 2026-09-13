"""Application lifecycle and scheduled-job integration tests."""

# Tests favor descriptive names over repeated docstrings and intentionally inspect internals.
# pylint: disable=missing-class-docstring,missing-function-docstring,protected-access

import asyncio
from typing import cast

import pytest
from pydantic import ValidationError

from axonx import Application, BaseComponent, BaseJob, BaseStep
from axonx.components.job import CronJob, SimpleJob
from axonx.components.plugin import LocalPluginComponent
from axonx.components.registry import R
from axonx.enums import JobMode
from axonx.schema import JobConfig


class _Logger:
    def info(self, *_args, **_kwargs):
        return None


def test_application_configures_logging_from_final_config(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "axonx.application.get_logger",
        lambda **kwargs: calls.append(kwargs) or _Logger(),
    )

    Application(log_to_console=False, log_to_file=False)

    assert calls == [
        {
            "log_dir": "logs",
            "log_to_console": False,
            "log_to_file": False,
            "force_init": True,
        }
    ]


def test_application_logs_configured_components_and_jobs(monkeypatch):
    messages = []

    class RecordingLogger:
        def info(self, message):
            messages.append(message)

    monkeypatch.setattr(
        "axonx.application.get_logger", lambda **_kwargs: RecordingLogger()
    )

    Application(
        log_to_file=False,
        components={
            "plugin": {"first": {"backend": "local"}},
            "task_manager": {"worker": {"backend": "local"}},
        },
        jobs={"inspect": {}, "submit": {}},
    )

    assert messages[-2:] == [
        "Components (2): plugin:first, task_manager:worker",
        "Jobs (2): inspect, submit",
    ]


def test_application_builds_plugin_jobs_before_freezing_the_graph(monkeypatch):
    class PluginStep(BaseStep):
        async def execute(self):
            self.response.answer = "plugin component ran"

    def discover(component):
        if component._discovered:
            return
        component.app_context.registry.add("plugin-step", PluginStep, "test-plugin")
        component._discovered = True

    monkeypatch.setattr(LocalPluginComponent, "discover", discover)
    monkeypatch.setattr(
        LocalPluginComponent,
        "job_configs",
        lambda self: {
            "plugin_job": JobConfig(steps=[{"backend": "plugin-step"}]),
            "plugin_cron": JobConfig(backend="cron", cron="0 2 * * *"),
        },
    )

    app = Application(components={"plugin": {"default": {"backend": "local"}}})

    assert type(app.context.jobs["plugin_job"]) is SimpleJob
    assert type(app.context.jobs["plugin_cron"]) is CronJob


async def test_plugin_job_can_run_a_plugin_component(monkeypatch):
    class PluginStep(BaseStep):
        async def execute(self):
            self.response.answer = "plugin component ran"

    def discover(component):
        if component._discovered:
            return
        component.app_context.registry.add("plugin-step", PluginStep, "test-plugin")
        component._discovered = True

    monkeypatch.setattr(LocalPluginComponent, "discover", discover)
    monkeypatch.setattr(
        LocalPluginComponent,
        "job_configs",
        lambda self: {"plugin_job": JobConfig(steps=[{"backend": "plugin-step"}])},
    )
    app = Application(components={"plugin": {"default": {"backend": "local"}}})

    async with app:
        response = await app.run_job("plugin_job")

    assert response.answer == "plugin component ran"


def test_application_rejects_plugin_job_name_conflicts(monkeypatch):
    monkeypatch.setattr(LocalPluginComponent, "discover", lambda self: None)
    monkeypatch.setattr(
        LocalPluginComponent,
        "job_configs",
        lambda self: {"shared": JobConfig()},
    )

    with pytest.raises(ValueError, match="both application config and plugins: shared"):
        Application(
            components={"plugin": {"default": {"backend": "local"}}},
            jobs={"shared": {}},
        )


def test_application_rejects_multiple_plugin_managers():
    with pytest.raises(ValueError, match="only one plugin manager"):
        Application(
            components={
                "plugin": {
                    "first": {"backend": "local"},
                    "second": {"backend": "local"},
                },
            },
        )


async def test_lifecycle_starts_background_jobs_last_and_closes_jobs_first():
    events = []

    class Dependency(BaseComponent):
        component_type = "test"

        async def _start(self):
            events.append("start dependency")

        async def _close(self):
            events.append("close dependency")

    class PublicJob(SimpleJob):
        async def _start(self):
            events.append("start public job")

        async def _close(self):
            events.append("close public job")

    class Runner(BaseJob):
        @property
        def mode(self):
            return JobMode.BACKGROUND

        async def _start(self):
            events.append("start background job")

        async def _close(self):
            events.append("close background job")

    with R.preserve(allow_mutation=True):
        R.register(Dependency, "order-dependency")
        R.register(PublicJob, "order-public")
        R.register(Runner, "order-background")
        app = Application(
            components={"test": {"dependency": {"backend": "order-dependency"}}},
            jobs={
                "background": {"backend": "order-background"},
                "public": {"backend": "order-public"},
            },
        )

    async with app:
        assert events == [
            "start dependency",
            "start public job",
            "start background job",
        ]

    assert events == [
        "start dependency",
        "start public job",
        "start background job",
        "close background job",
        "close public job",
        "close dependency",
    ]


async def test_run_job_rejects_unknown_name():
    app = Application()

    async with app:
        with pytest.raises(ValueError, match="Unknown job: 'missing'"):
            await app.run_job("missing")


def test_job_service_metadata_and_parameter_schema():
    app = Application(
        jobs={
            "public": {
                "description": "Public job",
                "parameters": {"properties": {"value": {"type": "integer"}}},
            },
            "private": {"enable_serve": False},
        },
    )

    public = app.context.jobs["public"]
    assert type(public) is SimpleJob
    assert public.backend == "simple"
    assert public.mode is JobMode.ON_DEMAND
    assert public.is_invocable
    assert public.is_servable
    assert public.info.name == "public"
    assert public.info.input_schema["type"] == "object"
    assert not app.context.jobs["private"].is_servable
    with pytest.raises(ValueError, match="Invalid arguments"):
        public.validate_arguments({"value": "not-an-integer"})

    with pytest.raises(ValidationError, match="JSON object"):
        Application(jobs={"invalid": {"parameters": {"type": "array"}}})


def test_workspace_path_expands_user_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))

    app = Application(workspace_dir="~/workspace")

    assert app.workspace_path == tmp_path / "workspace"


async def test_job_defaults_are_isolated_and_failure_stops_remaining_steps():
    calls = []

    class ProbeStep(BaseStep):
        async def execute(self):
            action = self.kwargs["action"]
            calls.append(action)
            if action == "append":
                self.context["items"].append("value")
                self.context.response.answer = list(self.context["items"])
            elif action == "stop":
                self.context.response.success = False

    with R.preserve(allow_mutation=True):
        R.register(ProbeStep, "job-probe")
        app = Application(
            jobs={
                "isolated": {
                    "defaults": {"items": []},
                    "steps": [{"backend": "job-probe", "action": "append"}],
                },
                "short-circuit": {
                    "steps": [
                        {"backend": "job-probe", "action": "stop"},
                        {"backend": "job-probe", "action": "unreachable"},
                    ],
                },
            },
        )

    async with app:
        first = await app.run_job("isolated")
        second = await app.run_job("isolated")
        failed = await app.run_job("short-circuit")

    assert first.answer == ["value"]
    assert second.answer == ["value"]
    assert not failed.success
    assert calls == ["append", "append", "stop"]


async def test_base_job_cancels_active_invocations_on_close():
    started = asyncio.Event()
    cancelled = asyncio.Event()

    class BlockingStep(BaseStep):
        async def execute(self):
            started.set()
            try:
                await asyncio.Future()
            finally:
                cancelled.set()

    with R.preserve(allow_mutation=True):
        R.register(BlockingStep, "blocking-job")
        app = Application(jobs={"blocking": {"steps": [{"backend": "blocking-job"}]}})

    await app.start()
    task = asyncio.create_task(app.run_job("blocking"))
    async with asyncio.timeout(1):
        await started.wait()
    await app.close()

    assert task.cancelled()
    assert cancelled.is_set()


async def test_cron_job_recovers_from_failure_and_stops_on_close():
    attempts = 0
    recovered = asyncio.Event()

    class FlakyStep(BaseStep):
        async def execute(self):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("first run fails")
            recovered.set()

    class FastCronJob(CronJob):
        def _next_delay(self):
            return 0.01

    with R.preserve(allow_mutation=True):
        R.register(FlakyStep, "flaky-background")
        R.register(FastCronJob, "fast-cron")
        app = Application(
            jobs={
                "ticker": {
                    "backend": "fast-cron",
                    "cron": "* * * * *",
                    "steps": [{"backend": "flaky-background"}],
                },
            },
        )

    async with app:
        async with asyncio.timeout(1):
            await recovered.wait()
        with pytest.raises(
            ValueError,
            match="does not support direct invocation.*background",
        ):
            await app.run_job("ticker")

    attempts_after_close = attempts
    await asyncio.sleep(0.03)
    assert attempts_after_close >= 2
    assert attempts == attempts_after_close


async def test_cron_job_cancels_an_active_invocation_on_close():
    started = asyncio.Event()
    cancelled = asyncio.Event()

    class BlockingStep(BaseStep):
        async def execute(self):
            started.set()
            try:
                await asyncio.Future()
            finally:
                cancelled.set()

    class ImmediateCronJob(CronJob):
        def _next_delay(self):
            return 0.0

    with R.preserve(allow_mutation=True):
        R.register(BlockingStep, "blocking-background")
        R.register(ImmediateCronJob, "immediate-cron")
        app = Application(
            jobs={
                "ticker": {
                    "backend": "immediate-cron",
                    "cron": "* * * * *",
                    "steps": [{"backend": "blocking-background"}],
                },
            },
        )

    await app.start()
    async with asyncio.timeout(1):
        await started.wait()
    await app.close()
    assert cancelled.is_set()


def test_cron_job_validates_schedule_and_timezone():
    app = Application(
        timezone="UTC",
        jobs={"scheduled": {"backend": "cron", "cron": "*/5 * * * *"}},
    )
    job = cast(CronJob, app.context.jobs["scheduled"])
    assert job.mode is JobMode.BACKGROUND
    assert not job.is_invocable
    assert not job.is_servable
    assert 0 < job._next_delay() <= 300

    with pytest.raises(ValueError, match="Invalid cron expression"):
        Application(jobs={"scheduled": {"backend": "cron", "cron": "invalid"}})
    with pytest.raises(ValueError, match="Unknown timezone"):
        Application(
            timezone="Not/A-Timezone",
            jobs={"scheduled": {"backend": "cron", "cron": "0 * * * *"}},
        )
