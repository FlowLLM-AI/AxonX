"""Read-only workspace browsing and preview tests."""

# pylint: disable=missing-function-docstring

import json
import os

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from axonx import Application
from axonx.steps.workspace.files import list_entries


async def _workspace_app(path):
    app = Application(
        workspace_dir=str(path),
        jobs={
            "list_workspace_entries": {"steps": [{"backend": "list_workspace_entries_step"}]},
            "preview_workspace_file": {
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "offset": {"type": "integer", "minimum": 0},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 5000},
                        "full": {"type": "boolean", "default": False},
                    },
                    "required": ["path"],
                    "additionalProperties": False,
                },
                "steps": [{"backend": "preview_workspace_file_step"}],
            },
            "delete_workspace_entry": {
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string", "minLength": 1}},
                    "required": ["path"],
                    "additionalProperties": False,
                },
                "steps": [{"backend": "delete_workspace_entry_step"}],
            },
            "delete_workspace_entries": {
                "parameters": {
                    "type": "object",
                    "properties": {
                        "paths": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": 200,
                            "items": {"type": "string", "minLength": 1},
                        },
                    },
                    "required": ["paths"],
                    "additionalProperties": False,
                },
                "steps": [{"backend": "delete_workspace_entries_step"}],
            },
        },
    )
    await app.start()
    return app


def test_workspace_metadata_filter_skips_incomplete_task_directories(tmp_path, caplog):
    etl = tmp_path / "etl"
    complete = etl / "etl#complete"
    incomplete = etl / "etl#incomplete"
    complete.mkdir(parents=True)
    incomplete.mkdir()
    (complete / "metadata.json").write_text("{}", encoding="utf-8")

    listing = list_entries(tmp_path, "etl", require_metadata=True)

    assert [entry["name"] for entry in listing["entries"]] == ["etl#complete"]
    assert "Skipping task directory without metadata.json" in caplog.text
    assert str(incomplete) in caplog.text


async def test_missing_workspace_directory_logs_warning_without_traceback(tmp_path, capsys):
    app = await _workspace_app(tmp_path)
    try:
        response = await app.run_job("list_workspace_entries", path="missing")
    finally:
        await app.close()

    log_output = capsys.readouterr().err
    assert response.success is False
    assert response.answer == "ValueError: Workspace directory does not exist"
    assert "WARNING" in log_output
    assert "Job failed: ValueError: Workspace directory does not exist" in log_output
    assert "Traceback" not in log_output


async def test_workspace_lists_directories_first_and_previews_supported_files(tmp_path):
    (tmp_path / "nested").mkdir()
    (tmp_path / "notes.txt").write_text("hello workspace", encoding="utf-8")
    pq.write_table(
        pa.table({"symbol": ["000001.SZ", "000002.SZ"], "close": [11.74, 3.06]}),
        tmp_path / "data.parquet",
    )
    app = await _workspace_app(tmp_path)
    try:
        listing = await app.run_job("list_workspace_entries", path="")
        text = await app.run_job("preview_workspace_file", path="notes.txt")
        parquet = await app.run_job("preview_workspace_file", path="data.parquet")
    finally:
        await app.close()

    assert [entry["name"] for entry in listing.answer["entries"]] == [
        "nested",
        "data.parquet",
        "notes.txt",
    ]
    assert text.answer["kind"] == "text"
    assert text.answer["content"] == "hello workspace"
    assert parquet.answer["kind"] == "parquet"
    assert parquet.answer["row_count"] == 2
    assert parquet.answer["row_group_count"] == 1
    assert parquet.answer["columns"] == ["symbol", "close"]
    assert parquet.answer["schema"] == [
        {"name": "symbol", "type": "string", "nullable": True},
        {"name": "close", "type": "double", "nullable": True},
    ]
    assert parquet.answer["rows"] == [["000001.SZ", 11.74], ["000002.SZ", 3.06]]
    assert parquet.answer["preview_limit"] == 5
    assert parquet.answer["full"] is False


async def test_workspace_can_read_parquet_fully_on_request(tmp_path):
    holdings = pa.array(
        [[{"rank": value + 1, "code": f"{value:06d}.SZ"}] for value in range(8)],
        type=pa.list_(pa.struct([("rank", pa.int64()), ("code", pa.string())])),
    )
    pq.write_table(
        pa.table({"value": list(range(8)), "holdings": holdings}),
        tmp_path / "data.parquet",
        row_group_size=3,
    )
    app = await _workspace_app(tmp_path)
    try:
        preview = await app.run_job("preview_workspace_file", path="data.parquet")
        full = await app.run_job("preview_workspace_file", path="data.parquet", full=True)
    finally:
        await app.close()

    assert preview.answer["rows"][0] == [0, [{"rank": 1, "code": "000000.SZ"}]]
    assert len(preview.answer["rows"]) == 5
    assert preview.answer["full"] is False
    assert len(full.answer["rows"]) == 8
    assert full.answer["rows"][-1] == [7, [{"rank": 8, "code": "000007.SZ"}]]
    assert full.answer["full"] is True


async def test_workspace_markdown_frontmatter_json_and_csv(tmp_path):
    (tmp_path / "readme.md").write_text(
        "---\ntitle: Research\ntags: [alpha, beta]\n---\n# Result\n",
        encoding="utf-8",
    )
    (tmp_path / "result.json").write_text('{"ok":true,"value":2}', encoding="utf-8")
    (tmp_path / "table.csv").write_text("name,value\na,1\nb,2\n", encoding="utf-8")
    app = await _workspace_app(tmp_path)
    try:
        markdown = await app.run_job("preview_workspace_file", path="readme.md")
        json_result = await app.run_job("preview_workspace_file", path="result.json")
        csv_result = await app.run_job("preview_workspace_file", path="table.csv", offset=1, limit=1)
    finally:
        await app.close()

    assert markdown.answer["frontmatter"] == {
        "title": "Research",
        "tags": ["alpha", "beta"],
    }
    assert markdown.answer["content"] == "# Result\n"
    assert json_result.answer["content"] == '{\n  "ok": true,\n  "value": 2\n}'
    assert json_result.answer["data"] == {"ok": True, "value": 2}
    assert csv_result.answer["columns"] == ["name", "value"]
    assert csv_result.answer["rows"] == [["b", "2"]]


async def test_workspace_csv_preview_accepts_bulk_limit(tmp_path):
    (tmp_path / "table.csv").write_text(
        "value\n" + "".join(f"{index}\n" for index in range(450)),
        encoding="utf-8",
    )
    app = await _workspace_app(tmp_path)
    try:
        result = await app.run_job("preview_workspace_file", path="table.csv", limit=5000)
    finally:
        await app.close()

    assert result.answer["limit"] == 5000
    assert len(result.answer["rows"]) == 450
    assert result.answer["rows"][-1] == ["449"]
    assert result.answer["has_more"] is False


async def test_workspace_previews_yaml_and_reports_invalid_yaml(tmp_path):
    (tmp_path / "config.yaml").write_text(
        "name: 研究配置\nenabled: true\nitems:\n  - alpha\n  - beta\n",
        encoding="utf-8",
    )
    (tmp_path / "broken.yml").write_text("items: [one, two\n", encoding="utf-8")
    app = await _workspace_app(tmp_path)
    try:
        valid = await app.run_job("preview_workspace_file", path="config.yaml")
        invalid = await app.run_job("preview_workspace_file", path="broken.yml")
    finally:
        await app.close()

    assert valid.answer["kind"] == "yaml"
    assert "name: 研究配置" in valid.answer["content"]
    assert valid.answer["data"] == {
        "name": "研究配置",
        "enabled": True,
        "items": ["alpha", "beta"],
    }
    assert valid.answer["parse_error"] is None
    assert invalid.answer["kind"] == "yaml"
    assert invalid.answer["parse_error"].startswith("Line 2, column 1:")


async def test_workspace_loads_large_structured_files_completely(tmp_path):
    payload = {"items": ["x" * 1024 for _ in range(520)]}
    (tmp_path / "large.json").write_text(json.dumps(payload), encoding="utf-8")
    app = await _workspace_app(tmp_path)
    try:
        result = await app.run_job("preview_workspace_file", path="large.json")
    finally:
        await app.close()

    assert result.answer["size"] > 512 * 1024
    assert result.answer["truncated"] is False
    assert result.answer["data"] == payload


async def test_workspace_rejects_path_escape_and_external_symlink(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    symlink = workspace / "outside-link.txt"
    try:
        symlink.symlink_to(outside)
    except OSError:
        pytest.skip("Symlinks are unavailable on this platform")

    app = await _workspace_app(workspace)
    try:
        escaped = await app.run_job("preview_workspace_file", path=os.path.relpath(outside, workspace))
        linked = await app.run_job("preview_workspace_file", path=symlink.name)
        listing = await app.run_job("list_workspace_entries", path="")
    finally:
        await app.close()

    assert not escaped.success
    assert "outside the configured workspace" in escaped.answer
    assert not linked.success
    assert "outside the configured workspace" in linked.answer
    assert listing.answer["entries"][0]["kind"] == "symlink"


async def test_workspace_deletes_files_and_directories_but_not_root(tmp_path):
    folder = tmp_path / "results"
    folder.mkdir()
    (folder / "output.txt").write_text("done", encoding="utf-8")
    file_path = tmp_path / "single.json"
    file_path.write_text("{}", encoding="utf-8")
    app = await _workspace_app(tmp_path)
    try:
        deleted_file = await app.run_job("delete_workspace_entry", path="single.json")
        deleted_folder = await app.run_job("delete_workspace_entry", path="results")
        rejected_root = await app.run_job("delete_workspace_entry", path=".")
    finally:
        await app.close()

    assert deleted_file.answer == {"deleted": "single.json", "kind": "file"}
    assert deleted_folder.answer == {"deleted": "results", "kind": "directory"}
    assert not file_path.exists()
    assert not folder.exists()
    assert not rejected_root.success
    assert "root cannot be deleted" in rejected_root.answer


async def test_workspace_batch_delete_validates_first_and_collapses_descendants(tmp_path):
    folder = tmp_path / "run"
    folder.mkdir()
    child = folder / "result.csv"
    child.write_text("value\n1\n", encoding="utf-8")
    other = tmp_path / "metadata.json"
    other.write_text("{}", encoding="utf-8")
    app = await _workspace_app(tmp_path)
    try:
        rejected = await app.run_job(
            "delete_workspace_entries",
            paths=["metadata.json", "missing.txt"],
        )
        assert not rejected.success
        assert other.exists()
        deleted = await app.run_job(
            "delete_workspace_entries",
            paths=["run/result.csv", "run", "metadata.json", "metadata.json"],
        )
    finally:
        await app.close()

    assert deleted.answer == {
        "deleted": [
            {"deleted": "run", "kind": "directory"},
            {"deleted": "metadata.json", "kind": "file"},
        ],
    }
    assert not folder.exists()
    assert not other.exists()
