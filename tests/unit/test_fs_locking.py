"""Filesystem writers fail fast or respect an explicit finite wait."""

from pathlib import Path
from time import monotonic

import pytest

from axonx.common.fs import file_lock


def test_default_contention_fails_and_unrelated_writers_proceed(tmp_path):
    path = tmp_path / "writer.lock"
    with file_lock(path):
        with pytest.raises(BlockingIOError, match="Resource is busy"):
            with file_lock(path):
                pytest.fail("Two writers acquired the same lease")
        with file_lock(tmp_path / "other.lock"):
            pass
    with file_lock(path):
        pass


def test_explicit_wait_expires_and_does_not_release_the_owner(tmp_path):
    path = tmp_path / "writer.lock"
    with file_lock(path):
        started = monotonic()
        with pytest.raises(TimeoutError, match="Lock wait exceeded"):
            with file_lock(path, timeout=0.02):
                pytest.fail("Contended lease was acquired")
        assert monotonic() - started < 1
        with pytest.raises(BlockingIOError):
            with file_lock(path):
                pass


@pytest.mark.parametrize("timeout", [-1, float("inf"), float("nan")])
def test_invalid_waits_create_no_files(tmp_path, timeout):
    with pytest.raises(ValueError, match="finite and nonnegative"):
        with file_lock(tmp_path / "writer.lock", timeout=timeout):
            pass
    assert not list(Path(tmp_path).iterdir())
