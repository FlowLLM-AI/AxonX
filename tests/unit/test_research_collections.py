"""Research outputs reference one artifact registry and one model manifest."""

import pytest
from pydantic import ValidationError

from axonx.enums import TaskType
from axonx.task.contracts import BasePredictOutputParams, BaseTrainOutputParams
from axonx.task.core import BaseOutputParams
from axonx.task.protocol import ModelCollection, task_protocol


def artifact(path):
    return {"path": path, "size": 1, "revision": "0:0"}


@pytest.mark.parametrize("members", [["model"], ["seed_0", "seed_42"]])
def test_collection_contracts_preserve_members(members):
    collection = ModelCollection(
        **task_protocol(TaskType.TRAIN),
        feature_protocol=task_protocol(TaskType.ETL),
        members={key: {"model_artifact": key, "model": {}} for key in members},
        artifacts={key: artifact(f"{key}/model.pt") for key in members},
    )
    train = BaseTrainOutputParams(train_rows=10, artifacts={"model_manifest": artifact("models.json")})
    assert set(collection.members) == set(members)
    assert set(train.model_dump()["artifacts"]) == {"model_manifest"}
    assert "protocol" not in train.model_dump()
    assert "model_files" not in train.model_dump()
    assert "model_sha256" not in collection.model_dump()["members"][members[0]]


@pytest.mark.parametrize("record", [{}, {"path": "../outside", "size": 1, "revision": "0:0"}])
def test_every_output_validates_artifact_records(record):
    with pytest.raises(ValidationError):
        BaseOutputParams(artifacts={"data": record})


def test_training_requires_a_manifest():
    with pytest.raises(ValidationError, match="model_manifest"):
        BaseTrainOutputParams(train_rows=10)


def test_prediction_score_mapping_has_one_source():
    protocol = {
        **task_protocol(TaskType.PREDICT),
        "model_identity": {"models_sha256": "0" * 64},
        "dates": ["20240102"],
        "score_columns": {"model": "score"},
        "predictions_revision": "0:0",
    }
    values = {
        "rows": 10,
        "date_range": {"start": "20240102", "end": "20240102"},
        "protocol": protocol,
    }
    output = BasePredictOutputParams(**values)
    assert output.protocol["score_columns"] == {"model": "score"}
    assert "score_columns" not in output.model_dump()
    with pytest.raises(ValidationError, match="differs from its protocol"):
        BasePredictOutputParams(**{**values, "protocol": {**protocol, "task_type": "inference"}})


def test_members_reference_registered_artifacts():
    with pytest.raises(ValidationError, match="unregistered"):
        ModelCollection(
            **task_protocol(TaskType.TRAIN),
            feature_protocol=task_protocol(TaskType.ETL),
            members={"model": {"model_artifact": "missing", "model": {}}},
            artifacts={"other": artifact("model.pt")},
        )
