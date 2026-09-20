"""Workspace handlers and task-archive application."""

import io
import tarfile
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from axonx.core import Application
from axonx.task.sync import TaskArchiveApplier
from axonx.workspace.browser import (
    delete_workspace_entries,
    list_workspace_entries,
)
from axonx.workspace.preview import preview_workspace_file
from axonx.workspace.staging import StagedFiles

TASK_ID = "etl#demo#run1234567890"
TASK_DIRECTORY = f"etl/{TASK_ID}"
TERMINAL_STATUS = (
    b'{"task_id":"etl#demo#run1234567890","run_id":"remote",'
    b'"task_type":"etl",'
    b'"state":"succeeded","exit_code":0}'
)


@pytest.mark.asyncio
async def test_streamed_upload_rejects_declared_size_mismatch(tmp_path):
    async def chunks():
        yield b"actual"

    with pytest.raises(ValueError, match="does not match declared size"):
        await StagedFiles(tmp_path).store_stream(chunks(), "file.bin", size=1)


def test_staged_file_is_verified_before_consumption(tmp_path):
    staged_files = StagedFiles(tmp_path)
    staged = staged_files.store(b"original", "file.bin")
    Path(staged.location).write_bytes(b"tampered")

    with pytest.raises(ValueError, match="does not match its path"):
        staged_files.file(staged.path)


def _archive(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, content in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(content)
            member.mtime = 0
            archive.addfile(member, io.BytesIO(content))
    return buffer.getvalue()


def test_task_archive_replaces_the_complete_directory(tmp_path):
    old = tmp_path / TASK_DIRECTORY
    old.mkdir(parents=True)
    (old / "stale.txt").write_text("stale", encoding="utf-8")
    staged = StagedFiles(tmp_path).store(
        _archive(
            {
                f"{TASK_DIRECTORY}/status.json": TERMINAL_STATUS,
                f"{TASK_DIRECTORY}/result.txt": b"new",
                f"{TASK_DIRECTORY}/nested/value.txt": b"nested",
            },
        ),
        "axonx-sync.tar.gz",
    )

    report = TaskArchiveApplier(tmp_path).apply(Path(staged.location), [], staged.path)

    assert report.applied == [TASK_DIRECTORY]
    assert not (old / "stale.txt").exists()
    assert (old / "result.txt").read_bytes() == b"new"
    assert (old / "nested/value.txt").read_bytes() == b"nested"


def test_invalid_task_archive_changes_nothing(tmp_path):
    old = tmp_path / TASK_DIRECTORY
    old.mkdir(parents=True)
    (old / "keep.txt").write_text("keep", encoding="utf-8")
    staged = StagedFiles(tmp_path).store(
        _archive({f"{TASK_DIRECTORY}/../../escape.txt": b"bad"}),
        "axonx-sync.tar.gz",
    )

    with pytest.raises(ValueError, match="not inside a task directory"):
        TaskArchiveApplier(tmp_path).apply(Path(staged.location), [], staged.path)

    assert (old / "keep.txt").read_text(encoding="utf-8") == "keep"
    assert not (tmp_path / "escape.txt").exists()


@pytest.mark.asyncio
async def test_sync_tasks_job_discards_consumed_and_refused_archives(tmp_path):
    staged_files = StagedFiles(tmp_path)
    valid = staged_files.store(
        _archive(
            {
                f"{TASK_DIRECTORY}/status.json": TERMINAL_STATUS,
                f"{TASK_DIRECTORY}/result.txt": b"ok",
            }
        ),
        "valid.tar.gz",
    )
    invalid = staged_files.store(b"not-an-archive", "invalid.tar.gz")
    app = Application(
        workspace_dir=str(tmp_path),
        enable_logo=False,
        log_to_console=False,
        log_to_file=False,
        components={"task_repository": {"default": {"backend": "local"}}},
        jobs={"sync_tasks": {"steps": [{"backend": "sync_tasks_step"}]}},
    )

    async with app:
        accepted = await app.run_job("sync_tasks", {"path": valid.path})
        rejected = await app.run_job("sync_tasks", {"path": invalid.path})

    assert accepted.success is True
    assert not (tmp_path / valid.path).exists()
    assert rejected.success is False
    assert not (tmp_path / invalid.path).exists()


def test_workspace_functions_own_only_browse_preview_and_delete(tmp_path):
    path = tmp_path / "note.txt"
    path.write_text("hello", encoding="utf-8")
    listing = list_workspace_entries(tmp_path)
    preview = preview_workspace_file(tmp_path, "note.txt")
    deleted = delete_workspace_entries(tmp_path, ["note.txt"])

    assert [entry.name for entry in listing.entries] == ["note.txt"]
    assert preview.content == "hello"
    assert deleted[0].deleted == "note.txt"
    assert not path.exists()


def test_workspace_listing_applies_filter_and_directory_order_before_limit(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("axonx.workspace.browser.MAX_DIRECTORY_ENTRIES", 2)
    (tmp_path / "a-file.txt").write_text("a", encoding="utf-8")
    for name in ("z-task", "y-task", "x-invalid"):
        (tmp_path / name).mkdir()
    (tmp_path / "z-task" / "metadata.json").write_text("{}", encoding="utf-8")
    (tmp_path / "y-task" / "metadata.json").write_text("{}", encoding="utf-8")

    listing = list_workspace_entries(
        tmp_path,
        ".",
        include=lambda path, entry: (
            entry.kind == "directory" and (path / "metadata.json").is_file()
        ),
    )

    assert listing.path == ""
    assert [entry.name for entry in listing.entries] == ["y-task", "z-task"]
    assert listing.truncated is False


def test_parquet_preview_uses_bounded_pagination(tmp_path):
    path = tmp_path / "values.parquet"
    pq.write_table(pa.table({"value": range(7)}), path)

    first = preview_workspace_file(tmp_path, path.name, offset=2, limit=3)
    last = preview_workspace_file(tmp_path, path.name, offset=5, limit=3)

    assert first.rows == [[2], [3], [4]]
    assert first.has_more is True
    assert last.rows == [[5], [6]]
    assert last.has_more is False


def test_workspace_operations_do_not_traverse_symlinks(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    (target / "note.txt").write_text("secret", encoding="utf-8")
    (tmp_path / "link").symlink_to(target, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        preview_workspace_file(tmp_path, "link/note.txt")
