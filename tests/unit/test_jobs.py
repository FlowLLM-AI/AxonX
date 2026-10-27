"""Verify Job contracts, invocation isolation, backpressure, and cancellation cleanup."""

import asyncio
import json
import os
import sys
from contextlib import aclosing
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from axonx.app.components.job import command
from axonx.app.components.job.base import RESPONSE_CALLBACKS, fold_events
from axonx.app.components.job.pipeline import PipelineJob
from axonx.app.components.registry import provider
from axonx.app.core.application import Application
from axonx.app.steps.base import BaseStep
from axonx.client.config import AXONX_CLI_REQUEST_ID, AXONX_SERVICE_TARGET
from axonx.client.events import LogEvent, ResultEvent
from axonx.client.models import JobResponse


@pytest.fixture
def make_app(tmp_path):
    @provider("callback")
    class CallbackStep(BaseStep):
        injected_parameters = {"depth": {"type": "integer", "minimum": 0}}

        async def execute(self):
            await self.kwargs["callback"](self)

    def make(*callbacks, **options):
        return Application(
            providers=(CallbackStep,),
            workspace_dir=str(tmp_path),
            log_to_console=False,
            log_to_file=False,
            jobs={
                "work": {"steps": [{"backend": "callback", "callback": callback} for callback in callbacks], **options}
            },
        )

    return make


def test_schemas_are_isolated_from_original_inputs_and_catalog_consumers(make_app):
    schema = {"properties": {"value": {"type": "integer"}}, "required": ["value"]}
    job = make_app(parameters=schema).context.jobs["work"]
    schema["properties"]["value"]["type"] = "string"
    for exported in (job.parameters, job.info.input_schema):
        exported["properties"]["value"]["type"] = "string"
    job.info.output_schema.clear()
    job.validate_arguments({"value": 1})
    with pytest.raises(ValueError, match="value:"):
        job.validate_arguments({"value": "1"})
    assert job.info.output_schema["type"] == "object"


@pytest.mark.parametrize(
    ("schema", "message"),
    [
        ({"type": "array"}, "must describe an object"),
        ({"properties": {"value": {"type": "invalid"}}}, "Invalid Job parameters schema"),
        ({"properties": {"target": {}}}, "reserved for transport targeting"),
    ],
)
def test_invalid_job_schemas_fail_at_construction(make_app, schema, message):
    # Construct directly so the Job contract is also checked outside ApplicationConfig.
    context = make_app().context
    with pytest.raises(ValueError, match=message):
        PipelineJob(app_context=context, parameters=schema)


def test_step_system_schema_stays_private_and_cannot_be_overridden(make_app):
    async def noop(_step):
        pass

    job = make_app(noop).context.jobs["work"]
    job.injected_parameters["depth"]["minimum"] = -1
    assert "depth" not in job.parameters["properties"]
    job.validate_system({"depth": 0})
    with pytest.raises(ValueError, match="System-owned arguments"):
        job.validate_arguments({"depth": 0})
    with pytest.raises(ValueError, match="Invalid system arguments"):
        job.validate_system({"depth": -1})
    with pytest.raises(ValueError, match="Invalid system arguments"):
        job.validate_system({"unknown": 1})
    with pytest.raises(ValueError, match="conflict with injected parameters"):
        make_app(noop, parameters={"properties": {"depth": {"type": "integer"}}})


@pytest.mark.parametrize("size", [0, -1, True, 1.5])
def test_event_buffer_must_be_a_positive_integer(make_app, size):
    with pytest.raises(ValueError, match="event_buffer_size"):
        make_app(event_buffer_size=size)


async def test_pipeline_calls_use_fresh_steps_contexts_and_responses(make_app):
    instances = []
    defaults = {"settings": {"items": [], "base": 1}, "depth": 99}
    arguments = {"settings": {"caller": 2}}
    original = deepcopy((defaults, arguments))

    async def first(step):
        instances.append(step)
        assert step.context["settings"] == {"items": [], "base": 1, "caller": 2}
        assert step.context["depth"] == 3
        step.context["settings"]["items"].append("first")
        step.response.answer = ["first"]
        await asyncio.sleep(0)

    async def second(step):
        assert step.context["settings"]["items"] == ["first"]
        step.response.answer.append("second")

    app = make_app(first, second, defaults=defaults)
    async with app:
        responses = await asyncio.gather(
            *(app.context.dispatcher.run("work", arguments, system={"depth": 3}) for _ in range(3))
        )
    assert [response.answer for response in responses] == [["first", "second"]] * 3
    assert len({id(step) for step in instances}) == 3
    assert all(step.context is None for step in instances)
    assert (defaults, arguments) == original
    responses[0].answer.append("changed")
    assert responses[1].answer == ["first", "second"]


async def test_pipeline_snapshots_step_configuration_and_copies_it_for_each_call(make_app):
    async def record(step):
        assert step.kwargs["settings"] == {"items": []}
        step.kwargs["settings"]["items"].append("used")
        step.response.answer = step.context["items"]
        step.context["items"].append("used")

    defaults = {"items": []}
    config = {"backend": "callback", "callback": record, "settings": {"items": []}}
    job = PipelineJob(app_context=make_app().context, steps=[config], defaults=defaults)
    defaults["items"].append("changed")
    config["settings"]["items"].append("changed")
    config["backend"] = "missing"

    async with job:
        responses = await asyncio.gather(*(job.run({}, {}) for _ in range(3)))
    assert all(response == JobResponse(answer=["used"]) for response in responses)


@pytest.mark.parametrize("raises", [False, True])
async def test_failed_steps_stop_the_pipeline_and_emit_one_terminal_result(make_app, raises):
    async def fail(step):
        await step.emit(LogEvent(content="before failure"))
        if raises:
            raise ValueError("rejected")
        step.response.success = False
        step.response.answer = "rejected"

    skipped = AsyncMock()
    app = make_app(fail, skipped, event_buffer_size=1)
    async with app:
        events = [event async for event in app.stream_job("work")]
    assert [event.kind for event in events] == ["log", "result"]
    assert not events[-1].success
    assert events[-1].answer == ("ValueError: rejected" if raises else "rejected")
    skipped.assert_not_awaited()


async def test_pipeline_backpressure_preserves_all_events_in_order(make_app):
    attempted, advanced = asyncio.Event(), asyncio.Event()

    async def produce(step):
        await step.emit(LogEvent(content="0"))
        await step.emit(LogEvent(content="1"))
        attempted.set()
        await step.emit(LogEvent(content="2"))
        advanced.set()
        for index in range(3, 100):
            await step.emit(LogEvent(content=str(index)))
        step.response.answer = "done"

    app = make_app(produce, event_buffer_size=1)
    async with app, aclosing(app.stream_job("work")) as stream:
        first = await anext(stream)
        await asyncio.wait_for(attempted.wait(), 1)
        assert not advanced.is_set()
        events = [first, *[event async for event in stream]]
    assert [event.content for event in events[:-1]] == [str(index) for index in range(100)]
    assert events[-1].response() == JobResponse(answer="done")


@pytest.mark.parametrize("stop", ["stream", "job", "application", "consumer"])
async def test_cancellation_waits_for_step_cleanup_and_skips_later_steps(make_app, stop):
    started, cleaned = asyncio.Event(), asyncio.Event()

    async def wait(step):
        try:
            await step.emit(LogEvent(content="ready"))
            started.set()
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0)
            cleaned.set()

    skipped = AsyncMock()
    app = make_app(wait, skipped)
    async with app:
        if stop == "consumer":
            consumer = asyncio.create_task(app.run_job("work"))
            await asyncio.wait_for(started.wait(), 1)
            consumer.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(consumer, 1)
        else:
            async with aclosing(app.stream_job("work")) as stream:
                assert (await anext(stream)).content == "ready"
                if stop == "stream":
                    await asyncio.wait_for(stream.aclose(), 1)
                else:
                    close = app.context.jobs["work"].close if stop == "job" else app.close
                    await asyncio.wait_for(close(), 1)
                    with pytest.raises(asyncio.CancelledError):
                        await anext(stream)
        assert cleaned.is_set()
        skipped.assert_not_awaited()


async def test_empty_pipeline_restarts_and_rejects_execution_while_stopped(make_app):
    job = make_app().context.jobs["work"]
    for _ in range(2):
        with pytest.raises(RuntimeError, match="not running"):
            await job.run({}, {})
        async with job:
            assert await job.run({}, {}) == JobResponse()


@pytest.mark.parametrize("cancel", ["close", "consumer", "both"])
async def test_cancelling_job_close_still_waits_for_step_cleanup(make_app, cancel):
    started, cleaning, release, cleaned = (asyncio.Event() for _ in range(4))

    async def wait(_step):
        try:
            started.set()
            await asyncio.Event().wait()
        finally:
            cleaning.set()
            await release.wait()
            cleaned.set()

    app = make_app(wait)
    async with app:
        consumer = asyncio.create_task(app.run_job("work"))
        close = None
        try:
            await asyncio.wait_for(started.wait(), 1)
            close = asyncio.create_task(app.context.jobs["work"].close())
            await asyncio.wait_for(cleaning.wait(), 1)
            if cancel in {"close", "both"}:
                close.cancel()
            if cancel in {"consumer", "both"}:
                consumer.cancel()
            done, _ = await asyncio.wait((close, consumer), timeout=0.05)
            assert not done
            release.set()
            outcomes = await asyncio.wait_for(asyncio.gather(close, consumer, return_exceptions=True), 1)
            if cancel in {"close", "both"}:
                assert isinstance(outcomes[0], asyncio.CancelledError)
            else:
                assert outcomes[0] is None
            assert isinstance(outcomes[1], asyncio.CancelledError)
            assert cleaned.is_set()
        finally:
            release.set()
            await asyncio.gather(consumer, *([close] if close is not None else []), return_exceptions=True)


@pytest.mark.parametrize("has_result", [False, True])
async def test_response_folding_closes_the_source_at_the_first_result(has_result):
    closed = asyncio.Event()

    async def events():
        try:
            yield LogEvent(content="log")
            if has_result:
                yield ResultEvent(answer="first")
                pytest.fail("Consumed events after the terminal result")
        finally:
            closed.set()

    response = await fold_events(events())
    assert closed.is_set()
    assert response == (
        JobResponse(answer="first")
        if has_result
        else JobResponse(answer="Stream produced no terminal result", success=False)
    )


def command_app(tmp_path, source, *, service=False):
    return Application(
        workspace_dir=str(tmp_path),
        log_to_console=False,
        log_to_file=False,
        command=(sys.executable, "-u", "-c", source),
        environment={"JOB_TEST_VALUE": "configured"},
        service={"backend": "http", "token": "test"} if service else None,
    )


async def test_command_preserves_exit_status_and_streams_beyond_the_capture_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(command, "OUTPUT_LIMIT", 6)
    app = command_app(tmp_path, "import sys; print('中文abc'); print('error', file=sys.stderr); sys.exit(3)")
    events = []

    async def emit(event):
        events.append(event)

    async with app:
        success, output = await command.run_command(app.context, (), emit)
    assert not success
    assert output == {
        "stdout": "中文",
        "stderr": "error\n",
        "exit_code": 3,
        "stdout_truncated": True,
        "stderr_truncated": False,
    }
    assert "".join(event.content for event in events if event.channel == "stdout") == "中文abc\n"
    assert "".join(event.content for event in events if event.channel == "stderr") == "error\n"


async def test_command_uses_service_environment_and_inherits_response_callbacks(tmp_path):
    source = (
        "import json, os, sys; "
        "print(json.dumps({'cwd': os.getcwd(), 'argv': sys.argv[1:], "
        "'environment': dict(os.environ)}))"
    )
    app = command_app(tmp_path, source, service=True)
    callbacks = []

    async def emit(event):
        request_id = json.loads(event.content)["environment"][AXONX_CLI_REQUEST_ID]
        assert app.context.service.cli_callbacks[request_id] is callbacks

    token = RESPONSE_CALLBACKS.set(callbacks)
    try:
        async with app:
            success, output = await command.run_command(app.context, ("a b", ";literal"), emit)
            assert success
            result = json.loads(output["stdout"])
            assert result["cwd"] == str(tmp_path.resolve())
            assert result["argv"] == ["a b", ";literal"]
            assert result["environment"]["JOB_TEST_VALUE"] == "configured"
            assert result["environment"][AXONX_SERVICE_TARGET] == app.context.service.local_target
            assert result["environment"]["AXONX_SERVICE_TOKEN"] == "test"
            assert not app.context.service.cli_processes
            assert not app.context.service.cli_callbacks
    finally:
        RESPONSE_CALLBACKS.reset(token)


async def test_failed_command_spawn_releases_response_callbacks(tmp_path):
    app = command_app(tmp_path, "", service=True)
    app.app_config.command = (str(tmp_path / "missing-command"),)
    async with app:
        with pytest.raises(FileNotFoundError):
            await command.run_command(app.context, (), AsyncMock())
        assert not app.context.service.cli_processes
        assert not app.context.service.cli_callbacks


async def test_log_consumer_failure_reaps_the_command_and_releases_ownership(tmp_path):
    app = command_app(tmp_path, "import os, time; print(os.getpid()); time.sleep(60)", service=True)
    process_ids = []

    async def emit(event):
        process_ids.append(int(event.content.strip()))
        raise ValueError("consumer failed")

    async with app:
        with pytest.raises(ExceptionGroup) as failure:
            await asyncio.wait_for(command.run_command(app.context, (), emit), 5)
        assert str(failure.value.exceptions[0]) == "consumer failed"
        assert not app.context.service.cli_processes
        assert not app.context.service.cli_callbacks
        with pytest.raises(ProcessLookupError):
            os.kill(process_ids[0], 0)


async def test_cancellation_during_spawn_still_reaps_the_created_process(tmp_path, monkeypatch):
    app = command_app(tmp_path, "import time; time.sleep(60)", service=True)
    create_subprocess = asyncio.create_subprocess_exec
    entered, release = asyncio.Event(), asyncio.Event()
    processes = []

    async def delayed_spawn(*args, **kwargs):
        process = await create_subprocess(*args, **kwargs)
        processes.append(process)
        entered.set()
        await release.wait()
        return process

    monkeypatch.setattr(command.asyncio, "create_subprocess_exec", delayed_spawn)
    async with app:
        task = asyncio.create_task(command.run_command(app.context, (), AsyncMock()))
        try:
            await asyncio.wait_for(entered.wait(), 5)
            task.cancel()
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 5)
            assert not app.context.service.cli_processes
            assert not app.context.service.cli_callbacks
            assert processes[0].returncode is not None
            with pytest.raises(ProcessLookupError):
                os.kill(processes[0].pid, 0)
        finally:
            release.set()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
