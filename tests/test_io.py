"""Tests for shared filesystem I/O primitives."""

# pylint: disable=missing-function-docstring,use-implicit-booleaness-not-comparison

import hashlib
import json

import pytest

from axonx.io import atomic_write, atomic_write_json, atomic_write_text, directory_sha256, file_sha256


def test_atomic_write_text_creates_parent_and_overwrites_with_unicode(tmp_path):
    path = tmp_path / "nested" / "状态.json"
    path.parent.mkdir()
    path.write_text("old", encoding="utf-8")

    atomic_write_text(path, "新状态")

    assert path.read_text(encoding="utf-8") == "新状态"
    assert list(path.parent.glob(f".{path.name}.*.tmp")) == []


def test_atomic_write_keeps_target_and_cleans_temporary_after_failure(tmp_path):
    path = tmp_path / "artifact.bin"
    path.write_bytes(b"stable")

    def fail(temporary):
        temporary.write_bytes(b"partial")
        raise RuntimeError("write failed")

    with pytest.raises(RuntimeError, match="write failed"):
        atomic_write(path, fail)

    assert path.read_bytes() == b"stable"
    assert list(tmp_path.glob(f".{path.name}.*.tmp")) == []


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_atomic_write_json_rejects_non_finite_numbers_without_replacing_target(tmp_path, value):
    path = tmp_path / "state.json"
    path.write_text('{"stable": true}', encoding="utf-8")

    with pytest.raises(ValueError):
        atomic_write_json(path, {"value": value})

    assert json.loads(path.read_text(encoding="utf-8")) == {"stable": True}
    assert list(tmp_path.glob(f".{path.name}.*.tmp")) == []


def test_file_sha256_hashes_file_contents(tmp_path):
    path = tmp_path / "data.bin"
    path.write_bytes(b"axonx\x00artifact")

    assert file_sha256(path) == hashlib.sha256(path.read_bytes()).hexdigest()


def test_directory_sha256_is_stable_and_honors_ignored_patterns(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "b.txt").write_text("b", encoding="utf-8")
    (source / "a.txt").write_text("a", encoding="utf-8")
    ignored = source / "demo.egg-info"
    ignored.mkdir()
    (ignored / "generated").write_text("first", encoding="utf-8")

    digest = directory_sha256(source, ignored_parts=("*.egg-info",))
    (ignored / "generated").write_text("second", encoding="utf-8")

    assert directory_sha256(source, ignored_parts=("*.egg-info",)) == digest
    (source / "a.txt").write_text("changed", encoding="utf-8")
    assert directory_sha256(source, ignored_parts=("*.egg-info",)) != digest
