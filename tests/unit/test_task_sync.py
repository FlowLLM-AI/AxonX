"""Task synchronization planning, archive, and durable state contracts."""

import io
import tarfile

import pytest

from axonx.components.sync.state import SyncStateStore
from axonx.task.sync import (
    SnapshotChangedError,
    TaskArchiveApplier,
    build_archive,
    pack_batches,
    plan_task,
)

TASK_ID = "etl#demo#run1234567890"
TASK_DIRECTORY = f"etl/{TASK_ID}"
STATUS = (
    b'{"task_id":"etl#demo#run1234567890","run_id":"remote",'
    b'"task_type":"etl","state":"succeeded","exit_code":0}'
)


def _task(tmp_path):
    directory = tmp_path / TASK_DIRECTORY
    directory.mkdir(parents=True)
    (directory / "status.json").write_bytes(STATUS)
    return directory


def test_one_oversized_file_rejects_the_whole_task_snapshot(tmp_path):
    directory = _task(tmp_path)
    (directory / "large.bin").write_bytes(b"x" * 2_000)

    plan = plan_task(tmp_path, TASK_ID, max_file_bytes=1_000)
    batches, rejected, deferred = pack_batches({TASK_ID: plan}, 10_000, 1)

    assert plan.transferable is False
    assert plan.rejected == ("large.bin",)
    assert batches == []
    assert rejected == [TASK_ID]
    assert deferred == []


def test_archive_build_fails_if_a_planned_file_changes(tmp_path):
    directory = _task(tmp_path)
    artifact = directory / "result.txt"
    artifact.write_text("before", encoding="utf-8")
    plan = plan_task(tmp_path, TASK_ID, max_file_bytes=1_000)
    artifact.write_text("after-change", encoding="utf-8")

    with pytest.raises(SnapshotChangedError):
        build_archive({TASK_ID: plan}, [TASK_ID], tmp_path / "snapshot.tar.gz")


def test_archive_applier_rejects_noncanonical_member_names(tmp_path):
    archive_path = tmp_path / "incoming.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        for name, content in {
            f"{TASK_DIRECTORY}/status.json": STATUS,
            f"./{TASK_DIRECTORY}/result.txt": b"ambiguous",
        }.items():
            member = tarfile.TarInfo(name)
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))

    with pytest.raises(ValueError, match="not canonical"):
        TaskArchiveApplier(tmp_path).apply(archive_path, [])


def test_sync_state_survives_restart_and_tracks_remote_acknowledgements(tmp_path):
    first = SyncStateStore(tmp_path, "10.0.0.8")
    first.save({TASK_ID})

    second = SyncStateStore(tmp_path, "10.0.0.8")
    assert second.load() == {TASK_ID}
