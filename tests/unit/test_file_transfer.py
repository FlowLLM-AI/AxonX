"""Complete directory replacement, extraction limits and failure cleanup."""

import io
import json
import os
import tarfile
from pathlib import Path

import pytest

from axonx.app.workspace import uploads as uploads_module
from axonx.app.workspace.core import Workspace
from axonx.client.files import MANIFEST_NAME, build_file_archive


def archive_bytes(path, directories, members):
    with tarfile.open(path, "w:gz") as archive:
        data = json.dumps(directories).encode()
        info = tarfile.TarInfo(MANIFEST_NAME)
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))
        for name, data, kind in members:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.type = kind
            info.linkname = "../../outside"
            archive.addfile(info, io.BytesIO(data))
    return path


def test_complete_replacement_removes_old_files_and_preserves_other_directories(tmp_path):
    workspace = Workspace(tmp_path / "target")
    old = workspace.resolve("reports/one/old.txt")
    old.parent.mkdir(parents=True)
    old.write_text("obsolete")
    unrelated = workspace.resolve("reports/other.txt")
    unrelated.write_text("keep")
    source = tmp_path / "source"
    source.mkdir()
    (source / "future-metadata.json").write_text('{"new_format": true}')
    archive = tmp_path / "files.tar.gz"
    build_file_archive({"reports/one": source}, archive)
    store = workspace.uploads
    for _ in range(2):
        report = store.replace(archive, 1_000_000)
        assert report == ["reports/one"]
    assert not old.exists()
    assert (old.parent / "future-metadata.json").read_text() == '{"new_format": true}'
    assert unrelated.read_text() == "keep"


@pytest.mark.parametrize(
    "directories,members",
    [
        (["../outside"], []),
        (["/absolute"], []),
        (["reports", "reports/nested"], []),
        (["tmp"], []),
        (["tmp/uploads/new"], []),
        (["tmp/files/new"], []),
        (["reports"], [("../outside", b"bad", tarfile.REGTYPE)]),
        (["reports"], [("other/file", b"bad", tarfile.REGTYPE)]),
        (["reports"], [("reports/link", b"", tarfile.SYMTYPE)]),
        (["reports"], [("reports/link", b"", tarfile.LNKTYPE)]),
        (["reports"], [("reports/file", b"a", tarfile.REGTYPE), ("reports/file", b"b", tarfile.REGTYPE)]),
        (["reports"], [(MANIFEST_NAME, b"[]", tarfile.REGTYPE)]),
    ],
)
def test_invalid_archive_leaves_existing_files_intact(tmp_path, directories, members):
    workspace = Workspace(tmp_path / "target")
    existing = workspace.resolve("reports/keep.txt")
    existing.parent.mkdir(parents=True)
    existing.write_text("keep")
    archive = archive_bytes(tmp_path / "bad.tar.gz", directories, members)
    with pytest.raises((ValueError, OSError)):
        workspace.uploads.replace(archive, 100_000)
    assert existing.read_text() == "keep"
    assert not list(workspace.resolve("tmp/files").glob("receive-*"))


def test_expanded_archive_budget_is_enforced_before_installation(tmp_path):
    archive = archive_bytes(
        tmp_path / "large.tar.gz", ["reports"], [("reports/large", b"x" * 100_000, tarfile.REGTYPE)]
    )
    assert archive.stat().st_size < 20_000
    workspace = Workspace(tmp_path / "target")
    with pytest.raises(ValueError, match="Expanded"):
        workspace.uploads.replace(archive, 20_000)
    assert not workspace.resolve("reports").exists()


def test_second_directory_install_failure_rolls_back_the_whole_batch(tmp_path, monkeypatch):
    workspace = Workspace(tmp_path / "target")
    for name in ("one", "two"):
        directory = workspace.resolve(name)
        directory.mkdir(parents=True)
        (directory / "keep").write_text(name)
    archive = archive_bytes(
        tmp_path / "batch.tar.gz",
        ["one", "two"],
        [
            ("one/new", b"one", tarfile.REGTYPE),
            ("two/new", b"two", tarfile.REGTYPE),
        ],
    )
    replace = os.replace

    def fail(incoming, target):
        if "incoming" in Path(incoming).parts and Path(target).name == "two":
            raise OSError("install failed")
        return replace(incoming, target)

    monkeypatch.setattr(uploads_module.os, "replace", fail)
    with pytest.raises(OSError, match="install failed"):
        workspace.uploads.replace(archive, 100_000)
    assert (workspace.resolve("one") / "keep").read_text() == "one"
    assert (workspace.resolve("two") / "keep").read_text() == "two"
    assert not workspace.resolve("one/new").exists()


def test_extended_tar_headers_are_included_in_the_expanded_budget(tmp_path):
    archive = tmp_path / "pax.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        data = json.dumps(["reports"]).encode()
        info = tarfile.TarInfo(MANIFEST_NAME)
        info.size = len(data)
        info.pax_headers = {"comment": "x" * 100_000}
        stream.addfile(info, io.BytesIO(data))
    assert archive.stat().st_size < 20_000
    workspace = Workspace(tmp_path / "target")
    with pytest.raises(ValueError, match="Expanded"):
        workspace.uploads.replace(archive, 20_000)
    assert not workspace.resolve("reports").exists()


def test_failed_rollback_keeps_original_files_available_for_recovery(tmp_path, monkeypatch):
    workspace = Workspace(tmp_path / "target")
    original = workspace.resolve("reports/original")
    original.parent.mkdir(parents=True)
    original.write_text("keep")
    archive = archive_bytes(tmp_path / "batch.tar.gz", ["reports"], [("reports/new", b"replacement", tarfile.REGTYPE)])
    replace = os.replace

    def fail(incoming, target):
        if "incoming" in Path(incoming).parts or "backup" in Path(incoming).parts:
            raise OSError("disk failure")
        return replace(incoming, target)

    monkeypatch.setattr(uploads_module.os, "replace", fail)
    with pytest.raises(OSError, match="backups retained"):
        workspace.uploads.replace(archive, 100_000)
    retained = list(workspace.resolve("tmp/files").glob("receive-*/backup/*/original"))
    assert len(retained) == 1 and retained[0].read_text() == "keep"
