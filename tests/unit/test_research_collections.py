"""Research producers use the same collection contract for one or many models."""

import pytest
from pydantic import ValidationError

from axonx.task.protocol import task_protocol
from axonx.enums import TaskType
from axonx.task.contracts import BasePredictOutputParams, BaseTrainOutputParams

PREDICT_PARAMS = {
    "predictions_file": "predictions.parquet",
    "rows": 10,
    "date_range": {"start": "20240102", "end": "20240102"},
}


@pytest.mark.parametrize("members", [["model"], ["seed_0", "seed_42"]])
def test_collection_contracts_preserve_members(members):
    model_files = {member: f"{member}/model.pt" for member in members}
    score_columns = {member: f"pred_{member}" for member in members}
    train_protocol = {
        **task_protocol(TaskType.TRAIN),
        "feature_protocol": task_protocol(TaskType.ETL),
        "members": {member: {"model_artifact": member, "model_sha256": "0" * 64, "model": {}} for member in members},
        "artifacts": {member: {"path": model_files[member], "sha256": "0" * 64} for member in members},
    }
    train = BaseTrainOutputParams(model_files=model_files, train_rows=10, protocol=train_protocol)
    prediction = BasePredictOutputParams(
        **PREDICT_PARAMS,
        score_columns=score_columns,
        protocol={
            **task_protocol(TaskType.PREDICT),
            "model_identity": {"models_sha256": "0" * 64},
            "dates": ["20240102"],
            "score_columns": score_columns,
            "predictions_sha256": "0" * 64,
        },
    )
    assert train.model_dump()["model_files"] == model_files
    assert prediction.model_dump()["score_columns"] == score_columns
    assert "model_file" not in train.model_dump()


@pytest.mark.parametrize("fields", [{}, {"model_files": {}}, {"model_file": "model.pt"}])
def test_train_requires_collection_contract(fields):
    with pytest.raises(ValidationError):
        BaseTrainOutputParams(**fields, train_rows=10)


@pytest.mark.parametrize("fields", [{}, {"score_columns": {}}])
def test_predict_requires_collection_contract(fields):
    with pytest.raises(ValidationError):
        BasePredictOutputParams(**PREDICT_PARAMS, **fields)


@pytest.mark.parametrize("producer", [TaskType.PREDICT, TaskType.INFERENCE])
def test_prediction_output_requires_matching_producer_and_scores(producer):
    protocol = {
        **task_protocol(producer),
        "model_identity": {"model": "test"},
        "dates": ["20240102"],
        "score_columns": {"model": "score"},
        "predictions_sha256": "0" * 64,
    }
    with pytest.raises(ValidationError, match="differs from its protocol"):
        BasePredictOutputParams(**PREDICT_PARAMS, score_columns={"model": "other"}, protocol=protocol)
    if producer == TaskType.INFERENCE:
        with pytest.raises(ValidationError, match="differs from its protocol"):
            BasePredictOutputParams(**PREDICT_PARAMS, score_columns=protocol["score_columns"], protocol=protocol)


def test_training_output_requires_matching_members():
    protocol = {
        **task_protocol(TaskType.TRAIN),
        "feature_protocol": task_protocol(TaskType.ETL),
        "members": {"model": {"model_artifact": "model", "model_sha256": "0" * 64, "model": {}}},
        "artifacts": {"model": {"path": "model.pt", "sha256": "0" * 64}},
    }
    with pytest.raises(ValidationError, match="members differ"):
        BaseTrainOutputParams(model_files={"other": "model.pt"}, train_rows=1, protocol=protocol)
