"""Workspace handlers and task-archive application."""

import hashlib
import io
import json
import tarfile
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from axonx.app.core import Application
from axonx.common.workspace import Workspace
from axonx.task.sync import TaskArchiveApplier

TASK_ID = "etl#demo#run1234567890"
TASK_DIRECTORY = f"etl/{TASK_ID}"
TERMINAL_STATUS = (
    b'{"version":1,"task_id":"etl#demo#run1234567890","run_id":"remote",'
    b'"task_type":"etl","machine_id":"source","pid":1234,"process_started_at":"2026-01-01T00:00:00Z",'
    b'"state":"succeeded","exit_code":0}'
)


@pytest.mark.asyncio
async def test_streamed_upload_rejects_declared_size_mismatch(tmp_path):

    async def chunks():
        yield b"actual"

    with pytest.raises(ValueError, match="does not match declared size"):
        await Workspace(tmp_path).stage_stream(chunks(), "file.bin", size=1)


def test_staged_file_resolves_without_reading_contents(tmp_path):
    staged_files = Workspace(tmp_path)
    staged = staged_files.stage_bytes(b"original", "file.bin")
    Path(staged["location"]).write_bytes(b"tampered")
    assert staged_files.staged_file(staged["path"]) == Path(staged["location"])


def _archive(files: dict[str, bytes]) -> bytes:
    metadata_path = f"{TASK_DIRECTORY}/metadata.json"
    if metadata_path in files:
        metadata = json.loads(files[metadata_path])
        metadata["replica"] = {
            "purpose": "display",
            "source_digest": "a" * 64,
            "policy_digest": "b" * 64,
            "files": {
                name.removeprefix(TASK_DIRECTORY + "/"): {
                    "size": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
                for name, content in files.items()
                if name != metadata_path
            },
            "omitted": {},
            "source_log_path": "",
        }
        files = {**files, metadata_path: json.dumps(metadata).encode()}
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
    staged = Workspace(tmp_path).stage_bytes(
        _archive(
            {
                f"{TASK_DIRECTORY}/metadata.json": TERMINAL_STATUS,
                f"{TASK_DIRECTORY}/result.txt": b"new",
                f"{TASK_DIRECTORY}/nested/value.txt": b"nested",
            }
        ),
        "axonx-sync.tar.gz",
    )
    report = TaskArchiveApplier(tmp_path).apply(Path(staged["location"]), [], staged["path"])
    assert report.applied == [TASK_DIRECTORY]
    assert not (old / "stale.txt").exists()
    assert (old / "result.txt").read_bytes() == b"new"
    assert (old / "nested/value.txt").read_bytes() == b"nested"


def test_invalid_task_archive_changes_nothing(tmp_path):
    old = tmp_path / TASK_DIRECTORY
    old.mkdir(parents=True)
    (old / "keep.txt").write_text("keep", encoding="utf-8")
    staged = Workspace(tmp_path).stage_bytes(
        _archive({f"{TASK_DIRECTORY}/../../escape.txt": b"bad"}), "axonx-sync.tar.gz"
    )
    with pytest.raises(ValueError, match="not inside a task directory"):
        TaskArchiveApplier(tmp_path).apply(Path(staged["location"]), [], staged["path"])
    assert (old / "keep.txt").read_text(encoding="utf-8") == "keep"
    assert not (tmp_path / "escape.txt").exists()


@pytest.mark.asyncio
async def test_sync_tasks_job_discards_consumed_and_refused_archives(tmp_path):
    staged_files = Workspace(tmp_path)
    valid = staged_files.stage_bytes(
        _archive({f"{TASK_DIRECTORY}/metadata.json": TERMINAL_STATUS, f"{TASK_DIRECTORY}/result.txt": b"ok"}),
        "valid.tar.gz",
    )
    invalid = staged_files.stage_bytes(b"not-an-archive", "invalid.tar.gz")
    app = Application(
        workspace_dir=str(tmp_path),
        enable_logo=False,
        log_to_console=False,
        log_to_file=False,
        components={"task_repository": {"default": {"backend": "local"}}},
        jobs={"sync_tasks": {"steps": [{"backend": "sync_tasks_step"}]}},
    )
    async with app:
        accepted = await app.run_job("sync_tasks", {"path": valid["path"]})
        rejected = await app.run_job("sync_tasks", {"path": invalid["path"]})
    assert accepted.success is True
    assert not (tmp_path / valid["path"]).exists()
    assert rejected.success is False
    assert not (tmp_path / invalid["path"]).exists()


def test_workspace_owns_browse_preview_and_delete(tmp_path):
    path = tmp_path / "note.txt"
    path.write_text("hello", encoding="utf-8")
    listing = Workspace(tmp_path).list_entries()
    preview = Workspace(tmp_path).preview_file("note.txt")
    deleted = Workspace(tmp_path).delete_entries(["note.txt"])
    assert listing["workspace_root"] == str(tmp_path.resolve())
    assert [entry["name"] for entry in listing["entries"]] == ["note.txt"]
    assert preview["content"] == "hello"
    assert deleted[0]["deleted"] == "note.txt"
    assert not path.exists()


def test_workspace_listing_applies_filter_and_directory_order_before_limit(tmp_path, monkeypatch):
    monkeypatch.setattr("axonx.common.workspace.core.MAX_DIRECTORY_ENTRIES", 2)
    (tmp_path / "a-file.txt").write_text("a", encoding="utf-8")
    for name in ("z-task", "y-task", "x-invalid"):
        (tmp_path / name).mkdir()
    (tmp_path / "z-task" / "metadata.json").write_text("{}", encoding="utf-8")
    (tmp_path / "y-task" / "metadata.json").write_text("{}", encoding="utf-8")
    listing = Workspace(tmp_path).list_entries(
        ".", include=lambda path, entry: entry["kind"] == "directory" and (path / "metadata.json").is_file()
    )
    assert listing["path"] == ""
    assert [entry["name"] for entry in listing["entries"]] == ["y-task", "z-task"]
    assert listing["truncated"] is False


def test_parquet_preview_uses_bounded_pagination(tmp_path):
    path = tmp_path / "values.parquet"
    pq.write_table(pa.table({"value": range(7)}), path)
    first = Workspace(tmp_path).preview_file(path.name, offset=2, limit=3)
    last = Workspace(tmp_path).preview_file(path.name, offset=5, limit=3)
    assert first["rows"] == [[2], [3], [4]]
    assert first["has_more"] is True
    assert last["rows"] == [[5], [6]]
    assert last["has_more"] is False


def test_workspace_operations_do_not_traverse_symlinks(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    (target / "note.txt").write_text("secret", encoding="utf-8")
    (tmp_path / "link").symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        Workspace(tmp_path).preview_file("link/note.txt")


def test_workspace_directory_pages_cover_all_entries(tmp_path, monkeypatch):
    monkeypatch.setattr("axonx.common.workspace.core.MAX_DIRECTORY_ENTRIES", 2)
    for name in ("2026", "2025", "Agent"):
        (tmp_path / name).mkdir()
    for name in ("a.json", "z.txt"):
        (tmp_path / name).write_text("{}", encoding="utf-8")
    pages = [Workspace(tmp_path).list_entries(offset=offset) for offset in (0, 2, 4, 6)]
    assert [[entry["name"] for entry in page["entries"]] for page in pages] == [
        ["2025", "2026"],
        ["Agent", "a.json"],
        ["z.txt"],
        [],
    ]
    assert [page["truncated"] for page in pages] == [True, True, False, False]
    with pytest.raises(ValueError, match="non-negative"):
        Workspace(tmp_path).list_entries(offset=-1)


@pytest.mark.asyncio
async def test_workspace_job_passes_directory_offset(tmp_path, monkeypatch):
    monkeypatch.setattr("axonx.common.workspace.core.MAX_DIRECTORY_ENTRIES", 2)
    for name in ("a", "b", "c"):
        (tmp_path / name).mkdir()
    app = Application(workspace_dir=str(tmp_path), jobs={"list_entries": {"steps": [{"backend": "workspace_list"}]}})
    async with app:
        response = await app.run_job("list_entries", {"offset": 2})
    assert response.success is True
    assert [entry.name for entry in response.answer.entries] == ["c"]
    assert response.answer.truncated is False


@pytest.mark.parametrize("extension", ["jsonl", "ndjson"])
def test_jsonl_preview_paginates_and_keeps_malformed_rows(tmp_path, extension):
    path = tmp_path / f"events.{extension}"
    path.write_bytes(b'\xef\xbb\xbf{"kind":"progress","percentage":25}\n{broken\nnull\n[1,2]\n')
    first = Workspace(tmp_path).preview_file(path.name, offset=0, limit=2)
    assert first["kind"] == "jsonl"
    assert first["rows"][0]["data"] == {"kind": "progress", "percentage": 25}
    assert first["rows"][0]["line"] == 1
    assert first["rows"][1]["parse_error"]
    assert first["rows"][1]["content"] == "{broken"
    assert first["has_more"]
    last = Workspace(tmp_path).preview_file(path.name, offset=2, limit=2)
    assert [row["line"] for row in last["rows"]] == [3, 4]
    assert [row["data"] for row in last["rows"]] == [None, [1, 2]]
    assert all((row["parse_error"] is None for row in last["rows"]))
    assert not last["has_more"]


def test_jsonl_preview_bounds_large_lines_and_preserves_next_record(tmp_path):
    from axonx.common.workspace.preview import TEXT_PREVIEW_BYTES

    path = tmp_path / "large.jsonl"
    path.write_bytes(b'"' + b"x" * (TEXT_PREVIEW_BYTES * 2) + b'"\n{"next":true}\n')
    first = Workspace(tmp_path).preview_file(path.name, limit=200)
    assert first["truncated"] and first["has_more"]
    assert len(first["rows"]) == 1
    assert first["rows"][0]["truncated"]
    assert first["rows"][0]["parse_error"] is None
    assert len(first["rows"][0]["content"]) <= TEXT_PREVIEW_BYTES
    second = Workspace(tmp_path).preview_file(path.name, offset=1)
    assert second["rows"][0]["data"] == {"next": True}
    assert not second["has_more"]


def test_jsonl_preview_handles_empty_and_partial_utf8_records(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_bytes(b"")
    assert Workspace(tmp_path).preview_file(path.name)["rows"] == []
    path.write_bytes(b'\xff\n{"open":')
    preview = Workspace(tmp_path).preview_file(path.name)
    assert len(preview["rows"]) == 2
    assert all((row["parse_error"] for row in preview["rows"]))
    assert not preview["has_more"]


@pytest.mark.parametrize(("suffix", "content"), [("json", '{"value": [1, 2]}'), ("yaml", "value: [1, 2]\n")])
def test_structured_preview_has_one_successful_representation(tmp_path, suffix, content):
    path = tmp_path / f"data.{suffix}"
    path.write_text(content)
    preview = Workspace(tmp_path).preview_file(path.name)
    assert preview["data"] == {"value": [1, 2]}
    assert preview["content"] == ""
    assert preview["parse_error"] is None


def test_cli_byte_budget_returns_marked_prefix_without_loading_full_json(tmp_path):
    (tmp_path / "large.json").write_text('{"large":"' + "x" * 10000 + '"}')
    preview = Workspace(tmp_path).preview_file("large.json", max_bytes=32)
    assert preview["truncated"] is True
    assert preview["data"] is None
    assert len(preview["content"].encode()) == 32
    assert preview["size"] > 10000
    assert Workspace(tmp_path).preview_file("large.json", max_bytes=20000)["data"]["large"] == "x" * 10000
    (tmp_path / "unicode.txt").write_text("中" * 10)
    prefix = Workspace(tmp_path).preview_file("unicode.txt", max_bytes=4)
    assert prefix["content"] == "中"
    assert prefix["truncated"]


@pytest.mark.parametrize("filename", ["unicode.txt", "unicode.md", "unicode.json", "unicode.yaml"])
def test_byte_budget_preserves_utf8_and_rejects_invalid_data(tmp_path, filename):
    path = tmp_path / filename
    path.write_bytes("中中".encode())
    prefix = Workspace(tmp_path).preview_file(filename, max_bytes=4)
    assert prefix["content"] == "中"
    assert prefix["truncated"]
    for invalid in (b"\xffinvalid text", b"\xe4\xb8", b"\xef", b"\xef\xbb"):
        path.write_bytes(invalid)
        with pytest.raises(ValueError, match="UTF-8"):
            Workspace(tmp_path).preview_file(filename, max_bytes=4)


def test_text_budget_can_exceed_default_and_markdown_keeps_frontmatter(tmp_path):
    from axonx.common.workspace.preview import TEXT_PREVIEW_BYTES

    content = "x" * (TEXT_PREVIEW_BYTES + 1)
    (tmp_path / "large.txt").write_text(content)
    default = Workspace(tmp_path).preview_file("large.txt")
    assert default["truncated"]
    complete = Workspace(tmp_path).preview_file("large.txt", max_bytes=len(content))
    assert complete["content"] == content
    assert not complete["truncated"]
    (tmp_path / "note.md").write_text("---\ntitle: note\n---\n" + "x" * 100)
    preview = Workspace(tmp_path).preview_file("note.md", max_bytes=24)
    assert preview["frontmatter"] == {"title": "note"}
    assert preview["content"] == "x" * 4
    assert preview["truncated"]


@pytest.mark.parametrize("budget", [True, False, 0, -1, 1.5, 33554433])
def test_preview_rejects_invalid_byte_budget_before_reading_files(tmp_path, budget):
    with pytest.raises(ValueError, match="max_bytes"):
        Workspace(tmp_path).preview_file("missing.json", max_bytes=budget)
