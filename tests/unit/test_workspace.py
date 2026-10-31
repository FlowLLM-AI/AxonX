"""Workspace models remain usable directly and through JSON transports."""

import json
import os
from pathlib import Path
from time import time

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from axonx.app.workspace.core import Workspace
from axonx.app.workspace.models import (
    CsvPreview,
    DeletedEntry,
    JsonlPreview,
    MarkdownPreview,
    ParquetPreview,
    StructuredPreview,
    TextPreview,
    UnsupportedPreview,
    WorkspaceEntry,
    WorkspaceListing,
)
from axonx.client.models import JobResponse, StagedFile


def test_listing_filters_typed_entries_before_pagination(tmp_path):
    (tmp_path / "directory").mkdir()
    (tmp_path / "unsupported.bin").write_bytes(b"binary")
    (tmp_path / "a.txt").write_text("hello")
    (tmp_path / "b.csv").write_text("value\n1\n")
    workspace = Workspace(tmp_path)
    seen = []

    def include(path, entry):
        assert isinstance(entry, WorkspaceEntry)
        assert path == tmp_path / entry.name
        seen.append(entry.name)
        return entry.kind == "directory" or entry.supported

    result = workspace.list_entries(include=include, offset=1)
    assert isinstance(result, WorkspaceListing)
    assert set(seen) == {"directory", "a.txt", "b.csv", "unsupported.bin"}
    assert [entry.name for entry in result.entries] == ["a.txt", "b.csv"]
    assert result.entries[0].size == 5
    assert result.model_dump()["entries"][0]["path"] == "a.txt"


@pytest.mark.parametrize(
    "filename,content,model",
    [
        ("text.txt", "hello", TextPreview),
        ("task.log", "INFO 开始执行\nERROR failed\n", TextPreview),
        ("task.LOG", "INFO uppercase extension\n", TextPreview),
        ("readme.md", "---\ntitle: Example\n---\nhello", MarkdownPreview),
        ("data.json", '{"value": 1}', StructuredPreview),
        ("data.yaml", "value: 1\n", StructuredPreview),
        ("table.csv", "value\n1\n2\n", CsvPreview),
        ("data.bin", "binary", UnsupportedPreview),
    ],
)
def test_preview_returns_models_with_transport_ready_fields(tmp_path, filename, content, model):
    (tmp_path / filename).write_text(content)
    preview = Workspace(tmp_path).preview_file(filename, limit=1)
    assert isinstance(preview, model)
    payload = json.loads(JobResponse(answer=preview).model_dump_json())["answer"]
    assert payload == preview.model_dump(mode="json")
    assert payload["size"] == len(content.encode())
    if isinstance(preview, TextPreview):
        assert preview.content == content
        assert not preview.truncated
        entry = Workspace(tmp_path).list_entries().entries[0]
        assert entry.supported and entry.preview_kind == "text"
    elif isinstance(preview, StructuredPreview):
        assert preview.data == {"value": 1}
        assert preview.parse_error is None
    elif isinstance(preview, MarkdownPreview):
        assert preview.frontmatter == {"title": "Example"}
        assert preview.content == "hello"
    elif isinstance(preview, CsvPreview):
        assert preview.rows == [["1"]]
        assert preview.has_more


@pytest.mark.parametrize("filename,content", [("bad.json", "{"), ("bad.yaml", "value: [")])
def test_structured_preview_preserves_errors_and_partial_content(tmp_path, filename, content):
    (tmp_path / filename).write_text(content)
    workspace = Workspace(tmp_path)
    preview = workspace.preview_file(filename)
    assert isinstance(preview, StructuredPreview)
    assert preview.parse_error and preview.content == content
    partial = workspace.preview_file(filename, max_bytes=1)
    assert partial.content == content[:1]
    if len(content) > 1:
        assert partial.truncated and partial.data is None


def test_optional_preview_distinguishes_absent_files_from_invalid_content_and_paths(tmp_path, monkeypatch):
    workspace = Workspace(tmp_path)
    assert workspace.preview_file("not-yet/published.json", allow_missing=True) is None
    with pytest.raises(ValueError, match="does not exist"):
        workspace.preview_file("not-yet/published.json")
    (tmp_path / "null.json").write_text("null")
    preview = workspace.preview_file("null.json", allow_missing=True)
    assert isinstance(preview, StructuredPreview) and preview.data is None
    (tmp_path / "invalid.json").write_text("{")
    assert workspace.preview_file("invalid.json", allow_missing=True).parse_error
    with pytest.raises(ValueError, match="parent traversal"):
        workspace.preview_file("../missing.json", allow_missing=True)
    (tmp_path / "link").symlink_to(tmp_path / "missing", target_is_directory=True)
    with pytest.raises(ValueError, match="symlinks"):
        workspace.preview_file("link/missing.json", allow_missing=True)
    with pytest.raises(ValueError, match="not a file"):
        workspace.preview_file("", allow_missing=True)
    stat = Path.stat

    def protected_stat(path, *args, **kwargs):
        if path.name == "private.json":
            raise PermissionError("Permission denied")
        return stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", protected_stat)
    with pytest.raises(PermissionError, match="Permission denied"):
        workspace.preview_file("private.json", allow_missing=True)


def test_jsonl_preview_keeps_typed_rows_and_invalid_record_errors(tmp_path):
    (tmp_path / "records.jsonl").write_text('{"x": 1}\nbad json\n{"x": 3}\n')
    preview = Workspace(tmp_path).preview_file("records.jsonl", offset=1, limit=1)
    assert isinstance(preview, JsonlPreview)
    assert preview.has_more
    assert preview.rows[0].line == 2
    assert preview.rows[0].parse_error
    assert preview.model_dump()["rows"][0]["content"] == "bad json"


def test_parquet_preview_preserves_schema_and_pagination(tmp_path):
    pq.write_table(pa.table({"value": [1, 2, 3]}), tmp_path / "table.parquet", row_group_size=1)
    preview = Workspace(tmp_path).preview_file("table.parquet", offset=1, limit=1)
    assert isinstance(preview, ParquetPreview)
    assert preview.rows == [[2]]
    assert preview.row_count == preview.row_group_count == 3
    assert preview.column_schema[0].name == "value"
    assert preview.column_schema[0].type == "int64"
    assert preview.has_more


async def test_staging_returns_models_and_cleans_up_incomplete_streams(tmp_path):
    workspace = Workspace(tmp_path)
    copied = workspace.uploads.stage_bytes(b"hello", "copy.txt")
    assert Path(copied.location).is_relative_to(tmp_path / "tmp/uploads")
    assert isinstance(copied, StagedFile)
    assert Path(copied.location).read_bytes() == b"hello"

    async def chunks():
        yield b"one"
        yield b"two"

    streamed = await workspace.uploads.stage_stream(chunks(), "stream.txt", size=6)
    assert isinstance(streamed, StagedFile)
    assert workspace.uploads.file(streamed.path).read_bytes() == b"onetwo"
    before = set(tmp_path.rglob("*"))
    with pytest.raises(ValueError, match="does not match"):
        await workspace.uploads.stage_stream(chunks(), "incomplete.txt", size=7)
    assert set(tmp_path.rglob("*")) == before
    assert json.loads(JobResponse(answer=streamed).model_dump_json())["answer"] == {
        "path": streamed.path,
        "location": streamed.location,
        "size": 6,
    }


def test_upload_retention_cannot_remove_tasks_sync_files_or_plugin_caches(tmp_path):
    expired = time() - 8 * 24 * 60 * 60
    paths = [tmp_path / "tmp" / name / "keep.bin" for name in ("tasks", "sync", "plugins")]
    for path in paths:
        path.parent.mkdir(parents=True)
        path.write_bytes(b"keep")
        os.utime(path, (expired, expired))
    Workspace(tmp_path).uploads.stage_bytes(b"new", "new.txt")
    assert all(path.read_bytes() == b"keep" for path in paths)


@pytest.mark.parametrize("streamed", [False, True])
@pytest.mark.parametrize("retention_days", [None, 1, 14])
async def test_each_upload_expires_old_staging_files_and_preserves_recent_files(
    tmp_path, monkeypatch, streamed, retention_days
):
    now = int(time())
    monkeypatch.setattr("axonx.app.workspace.uploads.time", lambda: now)
    cutoff = now - (7 if retention_days is None else retention_days) * 24 * 60 * 60
    staging = tmp_path / "staging"
    expired = staging / "batch" / "expired" / "old.txt"
    partial = staging / ".interrupted.tmp"
    boundary = staging / "boundary" / "keep.txt"
    recent = staging / "recent" / "keep.txt"
    outside = tmp_path / "keep.txt"
    for path, modified in (
        (expired, cutoff - 1),
        (partial, cutoff - 1),
        (boundary, cutoff),
        (recent, cutoff + 1),
        (outside, cutoff - 1),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"existing")
        os.utime(path, (modified, modified))
    options = {} if retention_days is None else {"upload_retention_days": retention_days}
    workspace = Workspace(tmp_path, copy_dir="staging", **options)
    assert expired.exists() and partial.exists()

    async def chunks():
        yield b"new"

    if streamed:
        uploaded = await workspace.uploads.stage_stream(chunks(), "new.txt", directory="staging/incoming")
    else:
        uploaded = workspace.uploads.stage_bytes(b"new", "new.txt", directory="staging/incoming")

    assert not expired.exists()
    assert not expired.parent.parent.exists()
    assert not partial.exists()
    for path in (boundary, recent, outside):
        assert path.read_bytes() == b"existing"
    assert Path(uploaded.location).read_bytes() == b"new"


@pytest.mark.parametrize("retention_days", [True, False, 0, -1, 1.5, "7", None])
def test_upload_retention_requires_a_positive_integer(tmp_path, retention_days):
    with pytest.raises(ValueError, match="retention_days must be a positive integer"):
        Workspace(tmp_path, upload_retention_days=retention_days)


def test_upload_cleanup_does_not_follow_symlinks(tmp_path):
    workspace = Workspace(tmp_path / "workspace")
    workspace.uploads.root.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    old = outside / "old.txt"
    old.write_bytes(b"keep")
    expired = time() - 7 * 24 * 60 * 60 - 60
    os.utime(old, (expired, expired))
    linked_file = workspace.uploads.root / "linked.txt"
    linked_directory = workspace.uploads.root / "linked-directory"
    linked_file.symlink_to(old)
    linked_directory.symlink_to(outside, target_is_directory=True)

    workspace.uploads.stage_bytes(b"new", "new.txt")

    assert old.read_bytes() == b"keep"
    assert linked_file.is_symlink()
    assert linked_directory.is_symlink()


@pytest.mark.parametrize("streamed", [False, True])
async def test_upload_cleanup_continues_after_a_file_cannot_be_deleted(tmp_path, monkeypatch, streamed):
    workspace = Workspace(tmp_path)
    blocked = workspace.uploads.root / "blocked" / "old.txt"
    removable = workspace.uploads.root / "removable" / "old.txt"
    expired = time() - 7 * 24 * 60 * 60 - 60
    for path in (blocked, removable):
        path.parent.mkdir(parents=True)
        path.write_bytes(b"old")
        os.utime(path, (expired, expired))
    unlink = Path.unlink

    def fail_blocked(path, *args, **kwargs):
        if path == blocked:
            raise PermissionError("Cannot remove staged file")
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_blocked)

    async def chunks():
        yield b"new"

    if streamed:
        uploaded = await workspace.uploads.stage_stream(chunks(), "new.txt")
    else:
        uploaded = workspace.uploads.stage_bytes(b"new", "new.txt")

    assert blocked.read_bytes() == b"old"
    assert not removable.exists()
    assert Path(uploaded.location).read_bytes() == b"new"


def test_deletion_validates_the_selection_then_returns_typed_roots(tmp_path):
    directory = tmp_path / "directory"
    directory.mkdir()
    (directory / "file.txt").write_text("hello")
    workspace = Workspace(tmp_path)
    with pytest.raises(ValueError, match="cannot contain parent traversal"):
        workspace.delete_entries(["directory", "../outside"])
    assert directory.is_dir()
    deleted = workspace.delete_entries(["directory/file.txt", "directory"])
    assert deleted == [DeletedEntry(deleted="directory", kind="directory")]
    assert not directory.exists()
