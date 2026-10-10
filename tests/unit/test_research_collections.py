"""Research producers use the same collection contract for one or many models."""

import pytest
from pydantic import ValidationError

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
    train = BaseTrainOutputParams(model_files=model_files, train_rows=10)
    prediction = BasePredictOutputParams(**PREDICT_PARAMS, score_columns=score_columns)
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
