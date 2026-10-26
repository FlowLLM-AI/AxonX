"""Exercise execution, composition and the Task-owned persistence primitives."""

import os
import subprocess
import sys

import pytest

from axonx.common.logging import LoggingConfig, configure_logging
from axonx.plugin import catalog
from axonx.plugin.models import PluginInfo
from axonx.task.builtins.demo import DemoTask
from axonx.task.core.composite import BaseCompositeTask
from axonx.task.models.params import BaseOutputParams
from axonx.task.runtime.executor import TaskExecutor
from axonx.task.storage.files import atomic_write, snapshot_file
from axonx.task.storage.locking import file_lock
from axonx.task.storage.workspace import read_entry, resolve_relative_path
from axonx.task.task_enums import TaskState
from axonx.task.sync.applier import TaskArchiveApplier


class ParentOutput(BaseOutputParams):
    result: int


class ParentTask(BaseCompositeTask):
    output_cls = ParentOutput

    def build_task_steps(self):
        yield self.add

    def add(self):
        self.state["result"] = self.run_task("demo", x=2, y=3).output["result"]

    def build_output_params(self):
        return ParentOutput(result=self.state["result"])


def test_executor_passes_the_resolver_to_nested_tasks(tmp_path):
    configure_logging(LoggingConfig(log_to_console=False, log_to_file=False))
    resolved = []

    def resolve(name):
        resolved.append(name)
        return {"parent": ParentTask, "demo": DemoTask}[name]

    result = TaskExecutor(tmp_path, resolve_task=resolve).execute("parent", {"task_name": "nested"})
    assert result.state == TaskState.SUCCEEDED
    assert result.output_params["result"] == 5
    assert resolved == ["parent", "demo"]
    child = result.children[0]
    assert child.state == TaskState.SUCCEEDED
    assert read_entry(tmp_path, child.task_id).parent_task_id == result.task_id


def test_failed_task_persists_its_terminal_status(tmp_path):
    configure_logging(LoggingConfig(log_to_console=False, log_to_file=False))
    with pytest.raises(RuntimeError, match="Demo failure requested"):
        TaskExecutor(tmp_path, resolve_task=lambda _: DemoTask).execute(
            "demo", {"task_name": "failure", "x": 1, "y": 2, "fail": True}
        )
    result = read_entry(tmp_path, "base#demo#failure")
    assert result.state == TaskState.FAILED
    assert result.exit_code != 0
    assert "Demo failure requested" in result.error


def test_catalog_only_loads_the_requested_task(monkeypatch):
    plugin = PluginInfo(distribution="example", version="1", tasks={"unrelated": "missing_package:Task"})
    monkeypatch.setattr(catalog, "list_installed_plugins", lambda: [plugin])
    assert catalog.get_task_definition("demo").name == "demo"
    with pytest.raises(ModuleNotFoundError):
        catalog.resolve_task("unrelated")


def test_catalog_rejects_plugin_names_that_shadow_builtins(monkeypatch):
    plugin = PluginInfo(distribution="example", version="1", tasks={"demo": "missing_package:Task"})
    monkeypatch.setattr(catalog, "list_installed_plugins", lambda: [plugin])
    with pytest.raises(ValueError, match="conflict"):
        catalog.resolve_task("demo")


def test_failed_atomic_publication_keeps_the_previous_file(tmp_path):
    target = tmp_path / "metadata.json"
    target.write_text("previous")

    def fail(temporary):
        temporary.write_text("partial")
        raise OSError("disk failure")

    with pytest.raises(OSError, match="disk failure"):
        atomic_write(target, fail)
    assert target.read_text() == "previous"
    assert list(tmp_path.iterdir()) == [target]


def test_isolated_snapshot_is_unchanged_when_source_is_rewritten(tmp_path):
    source, target = tmp_path / "source", tmp_path / "snapshot"
    source.write_text("original")
    snapshot_file(source, target, isolated=True)
    source.write_text("changed")
    assert target.read_text() == "original"


@pytest.mark.parametrize("path", ["", ".", "../outside", "/absolute"])
def test_task_mutation_paths_stay_inside_the_workspace(tmp_path, path):
    with pytest.raises(ValueError):
        resolve_relative_path(tmp_path, path)


def test_task_mutation_paths_reject_symlink_segments(tmp_path):
    (tmp_path / "link").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="symlinks"):
        resolve_relative_path(tmp_path, "link/metadata.json")


@pytest.mark.parametrize("budget", [0, -1, True, None])
def test_task_archive_budget_is_validated_before_mutation(tmp_path, budget):
    with pytest.raises(ValueError, match="positive integer"):
        TaskArchiveApplier(tmp_path, budget)


def test_online_publishers_cannot_enter_another_process_transaction(tmp_path):
    path = tmp_path / "publication.lock"
    code = (
        "import fcntl,sys; from pathlib import Path; "
        f"handle=Path({str(path)!r}).open('a+b'); fcntl.flock(handle,fcntl.LOCK_EX); "
        "print('ready',flush=True); sys.stdin.read()"
    )
    with subprocess.Popen(
        [sys.executable, "-c", code], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True
    ) as child:
        assert child.stdout.readline().strip() == "ready"
        with pytest.raises(BlockingIOError):
            with file_lock(path):
                pytest.fail("Entered another writer's transaction")
        child.communicate(timeout=5)
    with file_lock(path):
        assert os.path.isfile(path)
