import json

import pytest
from pydantic import ValidationError

from axonx.enums import TaskType
from axonx.task.core import BaseInputParams
from axonx.task.runtime.arguments import build_task_argv, parse_task_argv

ETL = "etl#native#prices"
TRAIN = "train#native#model"


def test_sources_are_normalized_and_serialized_as_a_string():
    params = BaseInputParams(source_tasks=f" {ETL}, {TRAIN} ")
    assert params.source_tasks == f"{ETL},{TRAIN}"
    assert params.model_dump()["source_tasks"] == f"{ETL},{TRAIN}"
    assert params.source_task(TaskType.ETL) == ETL
    assert params.source_task(TaskType.TRAIN) == TRAIN
    assert BaseInputParams.model_json_schema()["properties"]["source_tasks"]["type"] == "string"


@pytest.mark.parametrize("value", ["", "  "])
def test_empty_sources(value):
    assert BaseInputParams(source_tasks=value).source_tasks == ""
    assert BaseInputParams().source_tasks == ""


@pytest.mark.parametrize(
    "value", [[ETL], None, f"{ETL}，{TRAIN}", f"{ETL},", f",{ETL}", f"{ETL},,{TRAIN}", f"{ETL},{ETL}", "invalid"]
)
def test_invalid_sources_are_rejected(value):
    with pytest.raises(ValidationError):
        BaseInputParams(source_tasks=value)


def test_source_type_requires_exactly_one_match():
    with pytest.raises(ValueError, match="Missing source task"):
        BaseInputParams().source_task(TaskType.ETL)
    with pytest.raises(ValueError, match="Multiple source tasks"):
        BaseInputParams(source_tasks=f"{ETL},etl#native#other").source_task(TaskType.ETL)


def test_cli_and_structured_arguments_use_the_same_string():
    sources = f"{ETL},{TRAIN}"
    assert parse_task_argv(["--task", "demo", "--source-tasks", sources]) == ("demo", {"source_tasks": sources})
    assert parse_task_argv(build_task_argv("demo", {"source_tasks": sources})) == ("demo", {"source_tasks": sources})


def test_prediction_resolves_dataset_from_string_metadata(tmp_path):
    from axonx_alpha158.predict import LgbmPredictTask
    from axonx.task.storage.workspace import task_path

    etl_dir = task_path(tmp_path, ETL)
    etl_dir.mkdir(parents=True)
    (etl_dir / "metadata.json").write_text(
        json.dumps({"output_params": {"artifacts": {"dataset": {"path": "dataset.parquet"}}}})
    )
    task = LgbmPredictTask({"source_tasks": TRAIN}, workspace_path=tmp_path, reg_name="predict")
    task.state["train_metadata"] = {"input_params": {"source_tasks": ETL}}

    task.resolve_source_dataset()

    assert task.state["etl_task_id"] == ETL
    assert task.state["dataset_path"] == etl_dir / "dataset.parquet"
