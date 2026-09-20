"""Focused contracts for Job execution and scheduling."""

import asyncio
from typing import ClassVar

import pytest

from axonx.components.job import ArtifactEvent, PipelineJob
from axonx.components.registry import provider
from axonx.components.sync import BaseSyncComponent, SyncReport
from axonx.constants import AGENT_DEPTH_ARGUMENT
from axonx.core import Application
from axonx.steps.base import BaseStep


def _config(tmp_path, *, jobs, schedules=None):
    return {
        "workspace_dir": str(tmp_path),
        "enable_logo": False,
        "log_to_console": False,
        "log_to_file": False,
        "jobs": jobs,
        "schedules": schedules or {},
    }


def test_invalid_job_schema_is_reported_as_configuration_error(tmp_path):
    with pytest.raises(ValueError, match="Invalid Job parameters schema"):
        Application(
            **_config(
                tmp_path,
                jobs={"bad": {"parameters": {"type": "object", "properties": []}}},
            ),
        )


def test_step_rejects_an_irrelevant_component_option(tmp_path):
    with pytest.raises(TypeError, match="agent"):
        Application(
            **_config(
                tmp_path,
                jobs={
                    "bad": {"steps": [{"backend": "version_step", "agent": "default"}]}
                },
            )
        )


@pytest.mark.asyncio
async def test_drain_does_not_wait_when_step_is_cancelled_before_start():
    async def step():
        await asyncio.sleep(10)

    step_task = asyncio.create_task(step())
    step_task.cancel()

    async def consume():
        async for _ in PipelineJob._drain(asyncio.Queue(), step_task):
            pass

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(consume(), timeout=1)


@pytest.mark.asyncio
async def test_injected_parameters_are_private_and_system_owned(tmp_path):
    @provider("test_injected")
    class InjectedStep(BaseStep):
        injected_parameters: ClassVar = {
            AGENT_DEPTH_ARGUMENT: {"type": "integer", "minimum": 0},
        }

        async def execute(self):
            self.response.answer = self.context[AGENT_DEPTH_ARGUMENT]

    app = Application(
        providers=[InjectedStep],
        **_config(
            tmp_path,
            jobs={"nested": {"steps": [{"backend": "test_injected"}]}},
        ),
    )

    job = app.context.jobs["nested"]
    assert AGENT_DEPTH_ARGUMENT not in job.info.input_schema["properties"]
    assert AGENT_DEPTH_ARGUMENT in job.injected_parameters

    async with app:
        with pytest.raises(ValueError, match="System-owned arguments"):
            await app.run_job("nested", {AGENT_DEPTH_ARGUMENT: 0})
        response = await app.context.dispatcher.run(
            "nested",
            {},
            system={AGENT_DEPTH_ARGUMENT: 2},
        )
    assert response.answer == 2


@pytest.mark.asyncio
async def test_closing_stream_cancels_only_its_step(tmp_path):
    started = asyncio.Event()
    cancelled = asyncio.Event()

    @provider("test_waiting")
    class WaitingStep(BaseStep):
        async def execute(self):
            try:
                await self.emit(ArtifactEvent(path="ready"))
                started.set()
                await asyncio.Event().wait()
            finally:
                cancelled.set()

    app = Application(
        providers=[WaitingStep],
        **_config(
            tmp_path,
            jobs={"waiting": {"steps": [{"backend": "test_waiting"}]}},
        ),
    )

    async with app:
        stream = app.stream_job("waiting")
        event = await anext(stream)
        assert event.path == "ready"
        assert started.is_set()
        await stream.aclose()
        await asyncio.wait_for(cancelled.wait(), timeout=1)


@pytest.mark.asyncio
async def test_cron_scheduler_reuses_a_named_job_with_validated_arguments(tmp_path):
    seen: list[str] = []

    @provider("test_capture")
    class CaptureStep(BaseStep):
        async def execute(self):
            seen.append(self.context["value"])

    app = Application(
        providers=[CaptureStep],
        **_config(
                tmp_path,
                jobs={
                    "capture": {
                        "enable_serve": False,
                        "parameters": {
                            "type": "object",
                            "properties": {"value": {"type": "string"}},
                            "required": ["value"],
                            "additionalProperties": False,
                        },
                        "steps": [{"backend": "test_capture"}],
                    },
                },
                schedules={
                    "capture_every_minute": {
                        "job": "capture",
                        "cron": "* * * * *",
                        "arguments": {"value": "scheduled"},
                    },
                },
        ),
    )

    async with app:
        scheduler = app.context.schedulers["capture_every_minute"]
        await scheduler._trigger()
        await asyncio.gather(*tuple(scheduler._executions))

    assert seen == ["scheduled"]


@pytest.mark.asyncio
async def test_scheduled_sync_job_flushes_the_selected_component(tmp_path):
    flushed = []

    @provider("test_capture")
    class CaptureSync(BaseSyncComponent):
        async def flush(self):
            flushed.append(self.name)
            return SyncReport()

    app = Application(
        providers=[CaptureSync],
        **_config(
                tmp_path,
                jobs={
                    "sync_flush": {
                        "enable_serve": False,
                        "steps": [{"backend": "sync_flush_step", "sync": "replica"}],
                    },
                },
                schedules={
                    "workspace_sync": {
                        "job": "sync_flush",
                        "cron": "* * * * *",
                    },
                },
            ),
        components={"sync": {"replica": {"backend": "test_capture"}}},
    )

    async with app:
        scheduler = app.context.schedulers["workspace_sync"]
        await scheduler._trigger()
        await asyncio.gather(*tuple(scheduler._executions))

    assert flushed == ["replica"]


@pytest.mark.asyncio
async def test_schedule_arguments_are_validated_during_startup(tmp_path):
    app = Application(
        **_config(
            tmp_path,
            jobs={
                "required": {
                    "parameters": {
                        "type": "object",
                        "properties": {"value": {"type": "string"}},
                        "required": ["value"],
                    },
                },
            },
            schedules={
                "invalid": {
                    "job": "required",
                    "cron": "* * * * *",
                },
            },
        ),
    )

    with pytest.raises(ValueError, match="'value' is a required property"):
        await app.start()
