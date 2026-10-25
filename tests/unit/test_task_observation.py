"""Service Task queries observe independent exec processes without owning them."""

import asyncio
import os
import sys

import httpx

from axonx.app.config import resolve_app_config
from axonx.app.core import Application
from axonx.task.storage.workspace import read_entry, task_path


def application(root):
    config = resolve_app_config(log_config=False)
    config.update(workspace_dir=str(root), log_dir=str(root / "logs"), log_to_console=False, log_to_file=False)
    config["components"] = {"task_repository": {"default": {"backend": "local", "poll_interval": 0.01}}}
    config["jobs"] = {
        name: config["jobs"][name]
        for name in (
            "list_task_ids",
            "list_task_statuses",
            "status",
            "read_task_log",
            "wait_task",
            "stream_task",
            "get_task_graph",
        )
    }
    config["service"].update(token="test-token", web_enabled=False)
    return Application(**config)


async def test_exec_survives_service_restart_and_publishes_its_own_result(tmp_path):
    release = tmp_path / "release"
    code = """
import os, time
from pathlib import Path
from axonx.cli import main
from axonx.task.builtins import DemoTask
from axonx.task.runtime import executor
class Paused(DemoTask):
    def initialize(self):
        super().initialize()
        while not Path(os.environ['TASK_TEST_RELEASE']).exists():
            time.sleep(0.01)
executor.resolve_task = lambda name: Paused
raise SystemExit(main(['exec', '--task', 'demo', '--task-name', 'independent', '--x', '2', '--y', '3']))
"""
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        code,
        env={
            **os.environ,
            "AXONX_TASK_WORKSPACE_DIR": str(tmp_path),
            "AXONX_TASK_LOG_DIR": str(tmp_path / "logs"),
            "AXONX_TASK_TIMEZONE": "UTC",
            "TASK_TEST_RELEASE": str(release),
        },
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    app = application(tmp_path)
    task_id = "base#demo#independent"
    metadata = task_path(tmp_path, task_id) / "metadata.json"
    try:
        async with asyncio.timeout(15):
            while not metadata.exists() or not (status := read_entry(tmp_path, task_id)).steps:
                await asyncio.sleep(0.01)
        before = metadata.read_bytes()
        await app.start()
        assert (await app.run_job("status", {"task_id": task_id})).answer.run_id == status.run_id
        await app.close()
        assert process.returncode is None
        assert metadata.read_bytes() == before
        await app.start()
        assert metadata.read_bytes() == before
        release.touch()
        result = await asyncio.wait_for(
            app.run_job(
                "wait_task",
                {
                    "task_id": task_id,
                    "run_id": status.run_id,
                    "poll_interval": 0.01,
                },
            ),
            15,
        )
        assert result.success
        assert result.answer.output_params["result"] == 5
        assert result.answer.source.kind == "exec"
        stdout, stderr = await asyncio.wait_for(process.communicate(), 5)
        assert process.returncode == 0, stderr.decode()
        assert b'"result": 5' in stdout
        assert (await app.run_job("read_task_log", {"task_id": task_id, "run_id": status.run_id})).answer.content
        for job in ("read_task_log", "wait_task"):
            mismatch = await app.run_job(job, {"task_id": task_id, "run_id": "other"})
            assert not mismatch.success
            assert "Task run changed" in str(mismatch.answer)
    finally:
        release.touch()
        if process.returncode is None:
            process.kill()
        await process.communicate()
        await app.close()


async def test_task_mutation_jobs_are_not_exposed(tmp_path):
    config = resolve_app_config(log_config=False)
    assert not {"submit", "cancel", "delete_tasks"} & config["jobs"].keys()
    assert "task_manager" not in config["components"]
    app = application(tmp_path)
    assert set(app.context.components) == {"task_repository"}
    server = app.context.service.build_service(app)
    async with (
        app,
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=server),
            base_url="http://test",
            headers={"Authorization": "Bearer test-token"},
        ) as client,
    ):
        catalog = (await client.get("/jobs")).json()["answer"]["items"]
        assert not {"submit", "cancel", "delete_tasks"} & {item["name"] for item in catalog}
        for name in ("submit", "cancel", "delete_tasks"):
            for suffix in ("", "/events"):
                response = await client.post(f"/jobs/{name}{suffix}", json={"arguments": {}})
                assert response.status_code == 404
