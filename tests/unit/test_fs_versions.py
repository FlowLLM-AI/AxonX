"""Input revision checks read metadata only and honor caller deadlines."""

from pathlib import Path

import pytest

from axonx.utils.fs import file_versions


def test_revision_scan_reads_metadata_only_and_reports_progress(tmp_path, monkeypatch):
    path = tmp_path / "large.parquet"
    path.write_bytes(b"payload")
    reports = []

    def no_payload(*_args, **_kwargs):
        pytest.fail("A revision scan opened the payload")

    monkeypatch.setattr(Path, "open", no_payload)
    versions = file_versions([path, path], report=lambda **values: reports.append(values))
    assert versions == {path: f"7:{path.stat().st_mtime_ns}"}
    assert reports[-1]["completed"] == reports[-1]["total"] == 1
    assert reports[-1]["state"] == "done"


def test_expired_budget_rejects_even_an_empty_scan():
    class Expired:
        def check(self):
            raise TimeoutError("window expired")

    with pytest.raises(TimeoutError, match="window expired"):
        file_versions([], budget=Expired())
