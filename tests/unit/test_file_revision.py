"""Large-file metadata checks and snapshot publication guarantees."""

import os
import shutil
from pathlib import Path

import pytest

from axonx.task.storage.artifacts import artifact_record, prediction_protocol
from axonx.task.enums import TaskType
from axonx.common.fs import file_revision, snapshot_file


def test_large_artifact_registration_does_not_read_payload(tmp_path, monkeypatch):
    path = tmp_path / "large.parquet"
    with path.open("wb") as stream:
        stream.truncate(40 * 1024**3)

    def refuse_read(*args, **kwargs):
        raise AssertionError("Metadata checks must not read the payload")

    monkeypatch.setattr(Path, "open", refuse_read)
    record = artifact_record(path, tmp_path)
    protocol = prediction_protocol(TaskType.PREDICT, {"model": "v1"}, path, ["2026-01-01"], {"model": "score"})
    assert record["size"] == 40 * 1024**3
    assert record["revision"] == protocol["predictions_revision"] == file_revision(path)


@pytest.mark.parametrize("isolated", [False, True])
def test_snapshot_preserves_revision_across_copy_fallback(tmp_path, monkeypatch, isolated):
    source, target = tmp_path / "source", tmp_path / "target"
    source.write_bytes(b"original")
    os.utime(source, ns=(1700000000000000001, 1700000000000000001))

    def no_link(*args):
        raise OSError("cross-device link")

    monkeypatch.setattr(os, "link", no_link)
    snapshot_file(source, target, isolated=isolated)
    assert file_revision(source) == file_revision(target)
    source.write_bytes(b"modified")
    assert target.read_bytes() == b"original"
    assert file_revision(source) != file_revision(target)


def test_source_change_during_copy_does_not_publish(tmp_path, monkeypatch):
    source, target = tmp_path / "source", tmp_path / "target"
    source.write_bytes(b"before")
    target.write_bytes(b"previous snapshot")
    original = shutil.copy2

    def changing_copy(source, target):
        original(source, target)
        source.write_bytes(b"after copy changed")

    monkeypatch.setattr(shutil, "copy2", changing_copy)
    with pytest.raises(ValueError, match="Source changed"):
        snapshot_file(source, target, isolated=True)
    assert target.read_bytes() == b"previous snapshot"
    assert {p.name for p in tmp_path.iterdir()} == {"source", "target"}
