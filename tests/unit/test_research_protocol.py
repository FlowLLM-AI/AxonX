"""Portable contracts reject old schemas and protect model snapshots."""

import json

import pytest
from pydantic import ValidationError

from axonx.enums import TaskType
from axonx.task.protocol import (
    ModelCollection,
    PredictionProtocol,
    prediction_protocol,
    task_protocol,
    validate_protocol,
)
from axonx.task.storage import artifact_record
from axonx.task.storage.models import snapshot_model_collection
from axonx.task.storage.workspace import TaskMetadata
from axonx.utils.fs import atomic_write, file_sha256


@pytest.mark.parametrize("version", [None, 2, 3, "1", True, 1.0])
def test_old_protocols_are_rejected(version):
    record = {"task_type": "etl"}
    if version is not None:
        record["version"] = version
    with pytest.raises(ValidationError):
        validate_protocol(record)


def test_task_records_require_the_shared_header():
    record = {"task_id": "etl#etl#test", "run_id": "test", "task_type": TaskType.ETL}
    with pytest.raises(ValidationError):
        TaskMetadata(**record)
    assert TaskMetadata(version=1, **record).version == 1
    with pytest.raises(ValueError):
        validate_protocol(task_protocol(TaskType.ETL), TaskType.TRAIN)


def test_online_and_offline_predictions_share_one_identity(tmp_path):
    path = tmp_path / "predictions.parquet"
    path.write_bytes(b"predictions")
    identity = {"models_sha256": "a" * 64, "features_sha256": "b" * 64}
    records = [
        prediction_protocol(kind, identity, path, [20240103, 20240102], {"model": "score"})
        for kind in (TaskType.PREDICT, TaskType.INFERENCE)
    ]
    for record in records:
        assert PredictionProtocol.model_validate(record).model_identity == identity
        assert record["dates"] == ["20240102", "20240103"]
        assert "identities" not in record
        assert "models_sha256" not in record
    assert identity == {"models_sha256": "a" * 64, "features_sha256": "b" * 64}


def test_collection_snapshot_survives_source_replacement_and_rejects_corruption(
    tmp_path,
):
    model = tmp_path / "model.txt"
    model.write_bytes(b"original model")
    record = {
        **task_protocol(TaskType.TRAIN),
        "feature_protocol": task_protocol(TaskType.ETL),
        "members": {
            "model": {
                "model_artifact": "weights",
                "model": {"library": "test"},
            }
        },
        "artifacts": {"weights": artifact_record(model, tmp_path)},
    }
    manifest = tmp_path / "models.json"
    manifest.write_text(json.dumps(record))
    snapshot = snapshot_model_collection(manifest, tmp_path / "snapshot")
    atomic_write(model, lambda path: path.write_bytes(b"new model"))
    pinned = json.loads(snapshot.read_text())
    assert (snapshot.parent / pinned["artifacts"]["weights"]["path"]).read_bytes() == b"original model"
    with pytest.raises(ValueError, match="changed during snapshot"):
        snapshot_model_collection(manifest, tmp_path / "corrupt")
    record["members"]["model"]["model_artifact"] = "missing"
    with pytest.raises(ValidationError, match="unregistered"):
        ModelCollection.model_validate(record)


def test_manifest_refresh_is_rejected_before_snapshot(tmp_path):
    manifest = tmp_path / "models.json"
    manifest.write_bytes(b"original manifest")
    expected = file_sha256(manifest)
    atomic_write(manifest, lambda path: path.write_bytes(b"refreshed manifest"))
    with pytest.raises(ValueError, match="manifest changed"):
        snapshot_model_collection(manifest, tmp_path / "snapshot", expected_sha256=expected)
    assert not (tmp_path / "snapshot").exists()


def test_snapshot_resolves_relative_symlinks(tmp_path):
    from axonx.utils.fs import snapshot_file

    source = tmp_path / "model.pt"
    source.write_bytes(b"original")
    link = tmp_path / "link.pt"
    link.symlink_to(source.name)
    pinned = tmp_path / "other" / "model.pt"
    snapshot_file(link, pinned)
    atomic_write(source, lambda path: path.write_bytes(b"refreshed"))
    assert not pinned.is_symlink()
    assert pinned.read_bytes() == b"original"


@pytest.mark.parametrize(
    "changes",
    [
        {"dates": ["20240103", "20240102"]},
        {"dates": ["20240102", "20240102"]},
        {"score_columns": {"a": "score", "b": "score"}},
        {"score_columns": {"a": ""}},
    ],
)
def test_prediction_protocol_rejects_ambiguous_scope(changes):
    record = {
        **task_protocol(TaskType.PREDICT),
        "model_identity": {"model": "test"},
        "dates": ["20240102"],
        "score_columns": {"a": "score"},
        "predictions_sha256": "0" * 64,
        **changes,
    }
    with pytest.raises(ValidationError):
        PredictionProtocol.model_validate(record)
