"""Publication failures cannot expose partially committed online revisions."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from axonx.task.contracts import DeadlineBudget, WindowClock
from axonx.task.storage.online import OnlineStore, online_artifact, read_online_history


class Clock(WindowClock):
    def __init__(self):
        self.seconds = 0

    def now(self):
        return datetime(2026, 10, 12, tzinfo=UTC) + timedelta(seconds=self.seconds)

    def monotonic(self):
        return self.seconds

    def sleep(self, seconds):
        self.seconds += seconds


@pytest.fixture
def store(tmp_path):
    task = SimpleNamespace(
        task_dir=tmp_path,
        persistent_dir=tmp_path / "persistent",
        task_id="inference#test#fixed",
        context=SimpleNamespace(run_id="run"),
    )
    return OnlineStore(task)


def publish(store, day="20261012", trade_time="1445", **kwargs):
    source = store.task.task_dir / "signal.parquet"
    source.write_bytes(b"synthetic artifact")
    clock = Clock()
    return store.commit(
        history=store.history("0" * 64),
        trade_date=day,
        trade_time=trade_time,
        model_identity={"fingerprint": "fixed"},
        protocol={"version": 1, "task_type": "inference"},
        files={"signal": source},
        budget=DeadlineBudget(clock, clock.now() + timedelta(seconds=5)),
        **kwargs,
    )


def test_revisions_are_immutable_and_history_cutoffs_are_explicit(store):
    first, snapshot = publish(store)
    second, _ = publish(store, "20261013")
    revision, _ = publish(store)
    frozen = read_online_history(snapshot)
    history = store.history("0" * 64)
    assert len(frozen.commits) == 1
    assert [c.revision for c in history.commits] == [1, 1, 2]
    assert [c.commit_id for c in history.active()] == [revision.commit_id, second.commit_id]
    assert history.active("20261012")[0].commit_id == revision.commit_id
    assert not history.report_is_current(first)
    assert not history.report_is_current(second)
    assert history.report_is_current(revision)
    assert online_artifact(store.task.task_dir, first, "signal").read_bytes() == b"synthetic artifact"


@pytest.mark.parametrize("failure", ["copy", "validate", "swap", "deadline"])
def test_failures_keep_previous_manifest_and_remove_abandoned_files(store, monkeypatch, failure):
    import axonx.task.storage.online as module

    publish(store)
    before = store.manifest.read_bytes()
    previous = set((store.root / "commits").iterdir())
    original = module.shutil.copyfile

    def copy(source, target):
        if failure == "copy" or (failure == "swap" and str(target).endswith(".tmp")):
            raise OSError("synthetic copy failure")
        return original(source, target)

    def prepare(_commit, _snapshot):
        if failure == "validate":
            raise ValueError("invalid report")
        if failure == "deadline":
            raise TimeoutError("deadline")

    monkeypatch.setattr(module.shutil, "copyfile", copy)
    with pytest.raises((OSError, ValueError, TimeoutError)):
        publish(store, prepare=prepare)
    assert store.manifest.read_bytes() == before
    assert set((store.root / "commits").iterdir()) == previous
    assert not list(store.root.glob("*.tmp"))


def test_changed_strategy_and_tampered_artifacts_are_rejected(store):
    commit, _ = publish(store)
    with pytest.raises(ValueError, match="new task_name"):
        store.history("1" * 64)
    path = store.task.task_dir / commit.artifacts["signal"].path
    path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        online_artifact(store.task.task_dir, commit, "signal")


def test_scope_and_role_paths_are_validated_before_publication(store):
    with pytest.raises(ValidationError):
        publish(store, "20260230")
    assert not store.manifest.exists()
    assert not list((store.root / "commits").iterdir())
    with pytest.raises(ValueError, match="Invalid online artifact role"):
        source = store.task.task_dir / "source.parquet"
        source.write_bytes(b"data")
        clock = Clock()
        store.commit(
            history=store.history("0" * 64),
            trade_date="20261012",
            trade_time="1445",
            model_identity={"fingerprint": "fixed"},
            protocol={},
            files={"../escape": source},
            budget=DeadlineBudget(clock, clock.now() + timedelta(seconds=5)),
        )


def test_stale_history_cannot_overwrite_a_newer_commit(store):
    stale = store.history("0" * 64)
    publish(store)
    before = store.manifest.read_bytes()
    source = store.task.task_dir / "signal.parquet"
    clock = Clock()
    with pytest.raises(ValueError, match="history changed"):
        store.commit(
            history=stale,
            trade_date="20261013",
            trade_time="1445",
            model_identity={"fingerprint": "fixed"},
            protocol={"version": 1, "task_type": "inference"},
            files={"signal": source},
            budget=DeadlineBudget(clock, clock.now() + timedelta(seconds=5)),
        )
    assert store.manifest.read_bytes() == before


def test_preparation_cannot_publish_after_the_deadline(store):
    publish(store)
    before = store.manifest.read_bytes()
    source = store.task.task_dir / "signal.parquet"
    clock = Clock()

    def prepare(_commit, snapshot):
        assert snapshot.is_file()
        clock.sleep(6)

    with pytest.raises(TimeoutError):
        store.commit(
            history=store.history("0" * 64),
            trade_date="20261013",
            trade_time="1445",
            model_identity={"fingerprint": "fixed"},
            protocol={"version": 1, "task_type": "inference"},
            files={"signal": source},
            budget=DeadlineBudget(clock, clock.now() + timedelta(seconds=5)),
            prepare=prepare,
        )
    assert store.manifest.read_bytes() == before


@pytest.mark.parametrize("path", ["../outside", "/absolute", "a/../b", "a\\\\b", "a//b", "./b"])
def test_artifact_paths_must_be_portable_and_confined(path):
    from axonx.task.contracts.online import OnlineArtifact

    with pytest.raises(ValidationError, match="relative task path"):
        OnlineArtifact(path=path, size=0, sha256="0" * 64)


def test_publication_lock_wait_is_bounded(store):
    import fcntl

    store.root.mkdir(parents=True)
    with (store.root / "publication.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with pytest.raises(TimeoutError, match="Window deadline"):
            publish(store)
    assert not store.manifest.exists()


def test_later_signal_times_do_not_invalidate_earlier_reports(store):
    earlier, _ = publish(store)
    later, _ = publish(store, trade_time="1500")
    history = store.history("0" * 64)
    assert history.report_is_current(earlier)
    assert history.report_is_current(later)
    assert not history.report_is_current(earlier.model_copy(update={"commit_id": "f" * 32}))
    publish(store, trade_time="1430")
    assert not store.history("0" * 64).report_is_current(earlier)


@pytest.mark.parametrize("role", ["targets", "signals"])
def test_old_stock_commits_cannot_be_read_as_current_history(store, role):
    import json

    publish(store)
    value = json.loads(store.manifest.read_text())
    commit = value["commits"][0]
    commit["artifacts"][role] = commit["artifacts"]["signal"]
    with pytest.raises(ValidationError, match="Unsupported stock signals format"):
        from axonx.task.contracts import OnlineHistory

        OnlineHistory.model_validate(value)
