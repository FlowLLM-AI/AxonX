"""Read-only workspace browsing and preview tests."""

import json
import os

import pytest

from axonx import Application


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
                        "limit": {"type": "integer", "minimum": 1, "maximum": 200},
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
        },
    )
    await app.start()
    return app


async def test_workspace_lists_directories_first_and_previews_supported_files(tmp_path):
    (tmp_path / "nested").mkdir()
    (tmp_path / "notes.txt").write_text("hello workspace", encoding="utf-8")
    (tmp_path / "data.parquet").write_bytes(b"parquet-placeholder")
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
    assert parquet.answer == {"kind": "parquet", "size": 19}


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
