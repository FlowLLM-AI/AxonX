"""Plugin installation changes disk without refreshing loaded Task classes."""

import json
import shutil
import subprocess
import sys
from importlib import metadata
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest
import yaml

from axonx.plugin_kit import installer
from axonx.plugin_kit.wheel import inspect_wheel
from axonx.task.catalog import resolve_task

PACKAGE = "axonx_hot_update_test"
CONSUMER = "axonx_hot_update_consumer"


def wheel(tmp_path, package, files, tasks, components=None, jobs=None, extra_files=None):
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
        for name, content in (extra_files or {}).items():
            archive.writestr(name, content)
        record = f"{package}-1.0.dist-info/RECORD"
        archive.writestr(record, "".join(f"{name},,\n" for name in [*archive.namelist(), record]))
    return path


@pytest.fixture
def plugin_environment(tmp_path, monkeypatch):
    site = tmp_path / "site"
    site.mkdir()
    monkeypatch.syspath_prepend(str(site))
    distributions = metadata.distributions
    monkeypatch.setattr(metadata, "distributions", lambda: distributions(path=[str(site)]))

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
    for name in tuple(sys.modules):
        if any(name == package or name.startswith(package + ".") for package in (PACKAGE, CONSUMER)):
            sys.modules.pop(name, None)


def test_install_keeps_loaded_task_classes_and_new_interpreter_reads_installed_code(plugin_environment, tmp_path):
    import os

    old = resolve_task("hot_task")
    assert "minimum_fee" not in old.input_cls.model_fields
    artifact = inspect_wheel(plugin_environment.new)
    result = installer.install_plugin(artifact)
    assert "restart_required" not in result.model_dump()
    assert resolve_task("hot_task") is old
    source = f"from {PACKAGE}.task import Task; print('minimum_fee' in Task.input_cls.model_fields)"
    result = subprocess.run(
        [sys.executable, "-c", source],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": os.pathsep.join([str(plugin_environment.site), str(Path.cwd())])},
    )
    assert result.stdout.strip() == "True"


def test_install_failure_does_not_evict_loaded_modules(plugin_environment, monkeypatch):
    old = resolve_task("hot_task")

    def fail(*_args, **_kwargs):
        raise RuntimeError("pip failed")

    monkeypatch.setattr(installer, "install_artifact", fail)
    with pytest.raises(RuntimeError, match="pip failed"):
        installer.install_plugin(inspect_wheel(plugin_environment.new))
    assert resolve_task("hot_task") is old
