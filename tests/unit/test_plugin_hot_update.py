"""Exercise Task plugin updates in the same process that loaded the old code."""

import asyncio
import json
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from importlib import metadata
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from zipfile import ZipFile

import httpx
import pytest
import yaml

from axonx.components.client import HttpClient
from axonx.components.service import HttpService
from axonx.core import Application
from axonx.plugin_kit import discovery, environment, installer
from axonx.plugin_kit.loading import load_symbol
from axonx.plugin_kit.wheel import inspect_wheel
from axonx.task.catalog import get_task_definition, resolve_task
from axonx.task.core import BaseTask
from axonx.task.runtime.runner import TaskRunner
from axonx.workspace.staging import StagedFiles

PACKAGE = "axonx_hot_update_test"
CONSUMER = "axonx_hot_update_consumer"


def wheel(tmp_path, package, files, tasks, components=None, jobs=None):
    directory = tmp_path / package
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{package}-1.0-py3-none-any.whl"
    manifest = yaml.safe_dump({"tasks": tasks, "components": components or {}, "jobs": jobs or {}})
    with ZipFile(path, "w") as archive:
        archive.writestr(f"{package}/__init__.py", "")
        archive.writestr(f"{package}/plugin.yaml", manifest)
        for name, content in files.items():
            archive.writestr(f"{package}/{name}", content)
        archive.writestr(f"{package}-1.0.dist-info/METADATA", f"Metadata-Version: 2.1\nName: {package}\nVersion: 1.0\n")
        archive.writestr(f"{package}-1.0.dist-info/entry_points.txt", f"[axonx.plugins]\n{package} = {package}\n")
        archive.writestr(
            f"{package}-1.0.dist-info/WHEEL",
            "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
        archive.writestr(f"{package}-1.0.dist-info/RECORD", "")
    return path


@pytest.fixture
def plugin_environment(tmp_path, monkeypatch):
    site = tmp_path / "site"
    site.mkdir()
    monkeypatch.syspath_prepend(str(site))
    distributions = metadata.distributions
    monkeypatch.setattr(metadata, "distributions", lambda: distributions(path=[str(site)]))
    monkeypatch.setattr(environment, "_RESTART_REQUIRED", False)

    def install_files(artifact, **_kwargs):
        package = artifact.plugin_names[0]
        shutil.rmtree(site / package, ignore_errors=True)
        shutil.rmtree(site / f"{package}-1.0.dist-info", ignore_errors=True)
        with ZipFile(artifact.wheel) as archive:
            archive.extractall(site)
        (site / f"{package}-1.0.dist-info" / "direct_url.json").write_text(
            json.dumps({"archive_info": {"hashes": {"sha256": artifact.sha256}}}), encoding="utf-8"
        )

    def build(updated=False, components=None, jobs=None):
        fields = "    minimum_fee: float = 5\n" if updated else ""
        task_code = (
            "from axonx.task.builtins.demo import DemoTask\n"
            "from .params import Input\nfrom .internal import BONUS\n"
            "class Task(DemoTask):\n    input_cls = Input\n"
            "    def finish(self):\n        super().finish()\n        self.state['result'] += BONUS\n"
        )
        return wheel(
            tmp_path / ("new" if updated else "old"),
            PACKAGE,
            {
                "params.py": "from axonx.task.builtins.demo import DemoTaskInputParams\n"
                "class Input(DemoTaskInputParams):\n    fee: float = 0.01\n" + fields,
                "task.py": task_code,
                "internal/__init__.py": f"BONUS = {20 if updated else 1}\n",
            },
            {"hot_task": f"{PACKAGE}.task:Task", "added_task" if updated else "removed_task": f"{PACKAGE}.task:Task"},
            components,
            jobs,
        )

    old = build()
    new = build(True)
    consumer = wheel(
        tmp_path, CONSUMER, {"task.py": f"from {PACKAGE}.task import Task\n"}, {"consumer": f"{CONSUMER}.task:Task"}
    )
    install_files(inspect_wheel(old))
    install_files(inspect_wheel(consumer))
    monkeypatch.setattr(installer, "install_artifact", install_files)
    yield SimpleNamespace(site=site, old=old, new=new, install_files=install_files, build=build)
    environment.refresh_plugin_imports({PACKAGE, CONSUMER})


def install(path, tmp_path):
    return installer.install_staged_plugin(path, inspect_wheel(path).sha256, tmp_path / "artifacts")


def test_update_refreshes_classes_helpers_schema_and_registrations(plugin_environment, tmp_path):
    old = resolve_task("hot_task")
    assert resolve_task("consumer") is old
    assert "minimum_fee" not in get_task_definition("hot_task").input_schema["properties"]
    cache = {}
    assert load_symbol(f"{PACKAGE}.task:Task", BaseTask, kind="Task", modules=cache) is old

    result = install(plugin_environment.new, tmp_path)

    assert result.restart_required is False
    new = resolve_task("hot_task")
    assert new is not old
    assert resolve_task("consumer") is new
    assert resolve_task("added_task") is new
    with pytest.raises(ValueError, match="Unknown Task"):
        resolve_task("removed_task")
    assert load_symbol(f"{PACKAGE}.task:Task", BaseTask, kind="Task", modules=cache) is new
    assert "minimum_fee" in get_task_definition("hot_task").input_schema["properties"]
    task = new({"x": 2, "y": 3, "minimum_fee": 8}, workspace_path=tmp_path, reg_name="hot_task")
    assert task.input_params.minimum_fee == 8
    assert TaskRunner().run(task).exit_code == 0
    assert task.output["result"] == 25
    assert "minimum_fee" not in old.input_cls.model_fields
    assert install(plugin_environment.new, tmp_path).restart_required is False
    assert resolve_task("hot_task") is new


def test_first_install_is_available_without_restart(plugin_environment, tmp_path):
    shutil.rmtree(plugin_environment.site / PACKAGE)
    shutil.rmtree(plugin_environment.site / f"{PACKAGE}-1.0.dist-info")
    assert install(plugin_environment.new, tmp_path).restart_required is False
    assert "minimum_fee" in get_task_definition("hot_task").input_schema["properties"]


def test_failed_install_invalidates_partially_replaced_modules(plugin_environment, tmp_path, monkeypatch):
    old = resolve_task("hot_task")

    def fail(artifact, **kwargs):
        plugin_environment.install_files(artifact, **kwargs)
        raise RuntimeError("pip failed after replacing files")

    monkeypatch.setattr(installer, "install_artifact", fail)
    with pytest.raises(RuntimeError, match="pip failed"):
        install(plugin_environment.new, tmp_path)
    assert resolve_task("hot_task") is not old


def test_catalog_waits_for_installation(plugin_environment, tmp_path, monkeypatch):
    started, release, querying = Event(), Event(), Event()

    def delayed_install(artifact, **kwargs):
        started.set()
        assert release.wait(10)
        plugin_environment.install_files(artifact, **kwargs)

    def query():
        querying.set()
        return get_task_definition("hot_task")

    monkeypatch.setattr(installer, "install_artifact", delayed_install)
    with ThreadPoolExecutor(max_workers=2) as pool:
        installing = pool.submit(install, plugin_environment.new, tmp_path)
        try:
            assert started.wait(10)
            definition = pool.submit(query)
            assert querying.wait(10)
            with pytest.raises(FutureTimeout):
                definition.result(timeout=0.05)
        finally:
            release.set()
        assert installing.result(timeout=10).restart_required is False
        assert "minimum_fee" in definition.result(timeout=10).input_schema["properties"]


@pytest.mark.parametrize("old_contribution", [False, True])
@pytest.mark.parametrize("kind", ["components", "jobs"])
def test_live_contributions_require_restart(plugin_environment, tmp_path, kind, old_contribution):
    contribution = (
        {"step": {"test": f"{PACKAGE}.task:Task"}}
        if kind == "components"
        else {"test": {"steps": [{"backend": "version_step"}]}}
    )
    if old_contribution:
        old = plugin_environment.build(False, **{kind: contribution})
        plugin_environment.install_files(inspect_wheel(old))
        path = plugin_environment.new
    else:
        path = plugin_environment.build(True, **{kind: contribution})
    assert install(path, tmp_path).restart_required is True
    assert install(path, tmp_path).restart_required is True


def test_dependency_restart_hint_survives_identical_reinstall(plugin_environment, tmp_path, monkeypatch):
    def versions():
        updated = discovery.get_installed_plugin(PACKAGE).sha256 == inspect_wheel(plugin_environment.new).sha256
        return {"third-party": "2" if updated else "1"}

    monkeypatch.setattr(environment, "distribution_versions", versions)
    monkeypatch.setattr(installer, "distribution_versions", versions)
    assert install(plugin_environment.new, tmp_path).restart_required is True
    assert install(plugin_environment.new, tmp_path).restart_required is True


@pytest.mark.parametrize("failure", [False, True])
def test_uninstall_forgets_modules_and_registrations(plugin_environment, monkeypatch, failure):
    resolve_task("hot_task")
    resolve_task("consumer")

    def uninstall(*_args, **_kwargs):
        shutil.rmtree(plugin_environment.site / PACKAGE)
        shutil.rmtree(plugin_environment.site / f"{PACKAGE}-1.0.dist-info")
        return SimpleNamespace(returncode=int(failure), stderr="failed", stdout="")

    monkeypatch.setattr(installer.subprocess, "run", uninstall)
    if failure:
        with pytest.raises(RuntimeError, match="uninstall failed"):
            installer.uninstall_plugin(PACKAGE)
    else:
        assert installer.uninstall_plugin(PACKAGE).restart_required is False
    assert f"{PACKAGE}.task" not in sys.modules
    assert f"{CONSUMER}.task" not in sys.modules
    with pytest.raises(ValueError, match="Unknown Task"):
        resolve_task("hot_task")


async def test_remote_install_with_real_pip_refreshes_definition_and_submission(
    plugin_environment, tmp_path, monkeypatch
):
    old = resolve_task("hot_task")
    defaults = yaml.safe_load(Path("axonx/config/default.yaml").read_text(encoding="utf-8"))
    app = Application(
        workspace_dir=str(tmp_path / "workspace"),
        enable_logo=False,
        log_to_console=False,
        log_to_file=False,
        components={
            "task_repository": {"default": {"backend": "local"}},
            "task_manager": {"default": {"backend": "local"}},
        },
        jobs={name: defaults["jobs"][name] for name in ("install_plugin", "get_task_definition", "submit")},
    )

    def pip_install(artifact, **_kwargs):
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--no-deps",
                "--no-index",
                "--upgrade",
                "--target",
                str(plugin_environment.site),
                str(artifact.wheel),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

    monkeypatch.setattr(installer, "install_artifact", pip_install)
    manager = app.context.components["task_manager"]["default"]
    launched = []

    async def spawn(argv, _environment, task_id, _name, run_id):
        launched.append((argv, task_id, run_id))

    monkeypatch.setattr(manager._supervisor, "spawn", spawn)
    server = HttpService(token="secret", web_enabled=False).build_service(app)
    staged = StagedFiles(Path(app.context.app_config.workspace_dir))
    copied = staged.store(plugin_environment.new.read_bytes(), plugin_environment.new.name)
    staged_path = staged.file(copied.path)
    async with (
        server.router.lifespan_context(server),
        HttpClient(token="secret", transport=httpx.ASGITransport(app=server)) as client,
    ):
        response = await client.run_job("install_plugin", {"path": copied.path, "sha256": copied.sha256})
        assert response.success is True, response.answer
        assert response.answer["restart_required"] is False
        definition = await client.run_job("get_task_definition", {"task": "hot_task"})
        assert "minimum_fee" in definition.answer["input_schema"]["properties"]
        submitted = await client.run_job(
            "submit",
            {"task": "hot_task", "task_name": "new", "x": 2, "y": 3, "minimum_fee": 8},
        )
        assert submitted.success is True, submitted.answer
        status = await manager.get_status(submitted.answer["task_id"])
        assert status.config["minimum_fee"] == 8
        assert len(launched) == 1
        assert resolve_task("hot_task") is not old
    assert not staged_path.exists()


async def test_remote_install_waiters_do_not_block_service(plugin_environment, tmp_path, monkeypatch):
    defaults = yaml.safe_load(Path("axonx/config/default.yaml").read_text(encoding="utf-8"))
    app = Application(
        workspace_dir=str(tmp_path / "workspace"),
        enable_logo=False,
        log_to_console=False,
        log_to_file=False,
        components={
            "task_repository": {"default": {"backend": "local"}},
            "task_manager": {"default": {"backend": "local"}},
        },
        jobs={name: defaults["jobs"][name] for name in ("install_plugin", "get_task_definition", "submit", "version")},
    )
    started, release = Event(), Event()

    def delayed_install(artifact, **kwargs):
        started.set()
        assert release.wait(10)
        plugin_environment.install_files(artifact, **kwargs)

    monkeypatch.setattr(installer, "install_artifact", delayed_install)
    manager = app.context.components["task_manager"]["default"]
    launched = []

    async def spawn(*args):
        launched.append(args)

    monkeypatch.setattr(manager._supervisor, "spawn", spawn)
    staged = StagedFiles(app.workspace_path)
    copied = staged.store(plugin_environment.new.read_bytes(), plugin_environment.new.name)
    server = HttpService(token="secret", web_enabled=False).build_service(app)
    async with (
        server.router.lifespan_context(server),
        HttpClient(token="secret", transport=httpx.ASGITransport(app=server)) as client,
    ):
        installing = asyncio.create_task(
            client.run_job("install_plugin", {"path": copied.path, "sha256": copied.sha256})
        )
        querying = submitting = None
        try:
            assert await asyncio.wait_for(asyncio.to_thread(started.wait, 5), 6)
            querying = asyncio.create_task(client.run_job("get_task_definition", {"task": "hot_task"}))
            submitting = asyncio.create_task(
                client.run_job("submit", {"task": "hot_task", "task_name": "after", "x": 2, "y": 3, "minimum_fee": 8})
            )
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(querying), 0.05)
            assert not submitting.done()
            assert not launched
            assert (await asyncio.wait_for(client.run_job("version"), 2)).success
        finally:
            release.set()
            responses = await asyncio.gather(*(task for task in (installing, querying, submitting) if task is not None))
        assert all(response.success for response in responses)
        assert "minimum_fee" in responses[1].answer["input_schema"]["properties"]
        assert len(launched) == 1
