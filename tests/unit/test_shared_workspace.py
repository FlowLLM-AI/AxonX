"""Shared workspace mechanisms remain independent of application and Task policies."""

import asyncio
from pathlib import Path

import pytest

from axonx.app.core import Application
from axonx.common.workspace import Workspace
from axonx.task.builtins.demo import DemoTask


def test_construction_is_read_only_and_consumers_share_the_application_workspace(tmp_path):
    root = tmp_path / "missing"
    app = Application(
        workspace_dir=str(root),
        log_to_file=False,
        log_to_console=False,
        jobs={"list_entries": {"steps": [{"backend": "workspace_list"}]}},
    )
    step = next(app.context.jobs["list_entries"]._build_steps())
    assert step.workspace is app.context.workspace is app.workspace
    assert not root.exists()
    assert app.workspace.ensure() == root
    assert root.is_dir()
    task = DemoTask({"x": 1, "y": 2}, workspace_path=root, reg_name="demo")
    assert isinstance(task.workspace, Workspace)
    assert task.workspace.root == app.workspace.root == task.workspace_path


def test_untrusted_paths_and_explicit_external_inputs_have_distinct_contracts(tmp_path):
    workspace = Workspace(tmp_path / "workspace")
    external = tmp_path / "input.csv"
    external.write_text("value\n1\n")
    assert workspace.locate(external, external=True) == external
    for path in (external, "../input.csv"):
        with pytest.raises(ValueError, match="outside"):
            workspace.locate(path)
        with pytest.raises((TypeError, ValueError)):
            workspace.resolve(str(path))
    workspace.ensure()
    (workspace.root / "alias").symlink_to(external)
    with pytest.raises(ValueError, match="symlink"):
        workspace.resolve("alias")
    task = DemoTask({"x": 1, "y": 2}, workspace_path=workspace.root, reg_name="demo")
    assert task.resolve_workspace_path(external) == external


def test_delete_validates_all_roots_before_any_mutation(tmp_path):
    for name in ("keep", "protected"):
        (tmp_path / name).mkdir()
    calls = []

    def validate(root, targets):
        calls.append((root, targets))
        raise ValueError("protected by caller")

    workspace = Workspace(tmp_path, before_delete=validate)
    with pytest.raises(ValueError, match="protected by caller"):
        workspace.delete_entries(["keep", "protected"])
    assert calls == [(tmp_path, (tmp_path / "keep", tmp_path / "protected"))]
    assert (tmp_path / "keep").is_dir()
    with pytest.raises(ValueError, match="does not exist"):
        Workspace(tmp_path).delete_entries(["keep", "missing"])
    assert (tmp_path / "keep").is_dir()
    deleted = Workspace(tmp_path).delete_entries(["keep", "keep", "protected"])
    assert [entry["deleted"] for entry in deleted] == ["keep", "protected"]


async def test_workspace_jobs_preserve_typed_response_contracts(tmp_path):
    app = Application(
        workspace_dir=str(tmp_path),
        log_to_file=False,
        log_to_console=False,
        jobs={
            "list_entries": {"steps": [{"backend": "workspace_list"}]},
            "preview_file": {"steps": [{"backend": "workspace_preview"}]},
            "delete_entries": {"steps": [{"backend": "workspace_delete"}]},
        },
    )
    staged = app.workspace.stage_bytes(b'{"value":1}', "data.json")
    async with app:
        listing = await app.run_job("list_entries", {"path": str(Path(staged["path"]).parent)})
        assert listing.success
        assert [(entry.name, entry.preview_kind) for entry in listing.answer.entries] == [("data.json", "json")]
        preview = await app.run_job("preview_file", {"path": staged["path"]})
        assert preview.success
        assert preview.answer.model_dump() == {
            "kind": "json",
            "size": 11,
            "content": "",
            "data": {"value": 1},
            "parse_error": None,
            "truncated": False,
        }
        deleted = await app.run_job("delete_entries", {"paths": [staged["path"]]})
        assert deleted.success
        assert deleted.answer[0].model_dump() == {"deleted": staged["path"], "kind": "file"}
    app.workspace.discard_staged(staged["path"])


@pytest.mark.parametrize("copy_dir", ["tmp", ".", "nested/staging"])
async def test_staging_isolated_bytes_and_streams_share_cleanup(tmp_path, copy_dir):
    workspace = Workspace(tmp_path, copy_dir=copy_dir, transfer_budget_bytes=3)

    async def chunks():
        yield b"abc"

    first = workspace.stage_bytes(b"abc", "data.bin")
    second = await workspace.stage_stream(chunks(), "data.bin", size=3)
    assert first["path"] != second["path"]
    for staged in (first, second):
        assert workspace.staged_file(staged["path"]).read_bytes() == b"abc"
        assert Path(staged["location"]).is_relative_to(workspace.root)
        assert workspace.discard_staged(staged["path"]) == staged["path"]
        assert workspace.discard_staged(staged["path"]) == staged["path"]
    assert workspace.root.is_dir()
    assert not list(tmp_path.rglob("data.bin"))


async def test_stream_failure_budget_and_cancellation_remove_partial_files(tmp_path):
    workspace = Workspace(tmp_path, transfer_budget_bytes=3)

    async def over_budget():
        yield b"ab"
        yield b"cd"

    async def cancelled():
        yield b"ab"
        raise asyncio.CancelledError

    for chunks, error in ((over_budget, ValueError), (cancelled, asyncio.CancelledError)):
        with pytest.raises(error):
            await workspace.stage_stream(chunks(), "data.bin")
        assert not list(tmp_path.rglob("*"))
