"""Application lifecycle and scheduled-job integration tests."""

# Tests favor descriptive names over repeated docstrings and intentionally inspect internals.
# pylint: disable=missing-class-docstring,missing-function-docstring,protected-access

import asyncio

import pytest
from pydantic import ValidationError

from axonx import Application, BaseComponent, BaseJob, BaseStep
from axonx.components import R
from axonx.components.job import CronJob


async def test_lifecycle_starts_cron_last_and_closes_jobs_first():
    events = []

    class Dependency(BaseComponent):
        component_type = "test"

        async def _start(self):
            events.append("start dependency")

        async def _close(self):
            events.append("close dependency")

    class PublicJob(BaseJob):
        async def _start(self):
            events.append("start public job")

        async def _close(self):
            events.append("close public job")

    class Runner(CronJob):
        def __init__(self, **kwargs):
            super().__init__(cron="* * * * *", **kwargs)

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
        with pytest.raises(ValueError, match="managed in the background"):
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
    job = app.context.jobs["scheduled"]
    assert isinstance(job, CronJob)
    assert 0 < job._next_delay() <= 300

    with pytest.raises(ValueError, match="Invalid cron expression"):
        Application(jobs={"scheduled": {"backend": "cron", "cron": "invalid"}})
    with pytest.raises(ValueError, match="Unknown timezone"):
        Application(
            timezone="Not/A-Timezone",
            jobs={"scheduled": {"backend": "cron", "cron": "0 * * * *"}},
        )
