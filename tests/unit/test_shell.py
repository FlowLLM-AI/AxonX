"""Exercise shell Jobs through uploads, streams, disconnection and process cleanup."""

import asyncio
import shlex
from contextlib import aclosing
from copy import deepcopy

import httpx
import psutil
import pytest

from axonx.app.config.loader import ConfigLoader
from axonx.app.core.application import Application
from axonx.client.events import LogEvent


@pytest.fixture
def shell_app(tmp_path):
    config = ConfigLoader().resolve(log_config=False)["jobs"]["shell"]
    return Application(
        workspace_dir=str(tmp_path),
        log_dir=str(tmp_path / "logs"),
        log_to_console=False,
        log_to_file=False,
        jobs={"shell": deepcopy(config)},
        environment={"SHELL_TEST_VALUE": "configured"},
        service={"backend": "http", "token": "test", "web_enabled": False},
    )


def assert_dead(pid):
    try:
        assert psutil.Process(pid).status() in {psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD}
    except psutil.NoSuchProcess:
        pass


async def test_shell_upload_execute_and_auth(shell_app):
    script = b'set -euo pipefail\nprintf "%s\\n" "$SHELL_TEST_VALUE"\nprintf "stderr\\n" >&2\nprintf "done\\n"\n'
    async with shell_app as app:
        transport = httpx.ASGITransport(app=app.context.service.build_service(app))
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            unauthorized = await client.post("/jobs/shell", json={"arguments": {"command": "true"}})
            assert unauthorized.status_code == 401
            client.headers["Authorization"] = "Bearer test"
            upload = await client.post("/upload", files={"file": ("queue with spaces.sh", script)})
            assert upload.status_code == 200, upload.text
            location = upload.json()["answer"]["location"]
            response = await client.post(
                "/jobs/shell", json={"arguments": {"command": f"bash {shlex.quote(location)}"}}
            )
            assert response.status_code == 200, response.text
            result = response.json()
            assert result["success"], result
            assert result["answer"] == {
                "stdout": "configured\ndone\n",
                "stderr": "stderr\n",
                "exit_code": 0,
                "stdout_truncated": False,
                "stderr_truncated": False,
            }


async def test_shell_streams_both_channels_and_preserves_failure(shell_app, tmp_path):
    cwd = tmp_path / "working directory"
    cwd.mkdir()
    async with shell_app as app:
        events = [
            event
            async for event in app.stream_job(
                "shell", {"command": 'pwd; printf "out\\n"; printf "err\\n" >&2; exit 7', "cwd": str(cwd)}
            )
        ]
    stdout = "".join(event.content for event in events if isinstance(event, LogEvent) and event.channel == "stdout")
    stderr = "".join(event.content for event in events if isinstance(event, LogEvent) and event.channel == "stderr")
    assert str(cwd) in stdout and "out\n" in stdout and stderr == "err\n"
    assert not events[-1].success and events[-1].answer["exit_code"] == 7


@pytest.mark.parametrize("stop", ["complete", "application"])
async def test_shell_disconnect_keeps_script_owned_until_completion_or_shutdown(shell_app, tmp_path, stop):
    async with shell_app as app:
        async with aclosing(
            app.stream_job(
                "shell", {"command": "echo $$; while [ ! -f release ]; do sleep 0.01; done; touch first; touch second"}
            )
        ) as events:
            event = await asyncio.wait_for(anext(events), 5)
            assert isinstance(event, LogEvent)
            pid = int(event.content)
        job = app.context.jobs["shell"]
        assert pid in app.context.service.command_processes and job._active_runs
        assert not (tmp_path / "first").exists()
        if stop == "complete":
            (tmp_path / "release").touch()
            await asyncio.wait_for(asyncio.gather(*job._active_runs), 5)
            assert (tmp_path / "first").exists() and (tmp_path / "second").exists()
        else:
            await asyncio.wait_for(app.close(), 5)
            assert not (tmp_path / "second").exists()
        assert_dead(pid)
        assert not app.context.service.command_processes
        assert not app.context.service.cli_callbacks


async def test_shell_service_shutdown_reaps_descendants(shell_app):
    async with shell_app as app:
        async with aclosing(app.stream_job("shell", {"command": 'sleep 60 & printf "%s %s\\n" $$ $!; wait'})) as events:
            event = await asyncio.wait_for(anext(events), 5)
            parent, child = map(int, event.content.split())
        await asyncio.wait_for(app.close(), 5)
        assert_dead(parent)
        assert_dead(child)


async def test_shell_success_reaps_children_that_keep_output_pipes_open(shell_app):
    async with shell_app as app:
        response = await asyncio.wait_for(
            app.run_job("shell", {"command": "sleep 0.1; sleep 60 & printf '%s\\n' $!"}), 5
        )
        assert response.success, response.answer
        assert_dead(int(response.answer["stdout"]))


@pytest.mark.parametrize("values", [{}, {"command": "true", "background": True}, {"command": "true", "unknown": 1}])
async def test_shell_rejects_invalid_job_inputs(shell_app, values):
    async with shell_app as app:
        with pytest.raises(ValueError):
            await app.run_job("shell", values)


@pytest.mark.parametrize("values", [{"command": "  "}, {"command": "true", "cwd": "/missing-shell-directory"}])
async def test_shell_invalid_commands_fail_without_starting_processes(shell_app, values):
    async with shell_app as app:
        response = await app.run_job("shell", values)
        assert not response.success
        assert not app.context.service.command_processes
