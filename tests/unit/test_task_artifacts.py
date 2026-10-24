"""Research artifact consumers require a successful upstream execution."""

import json

import pytest

from axonx.task.enums import TaskState, TaskType
from axonx.task import BaseOutputParams, BaseTask
from axonx.task.builtins.stock.backtest import BaseStockBacktestTask
from axonx.task.runtime.runner import TaskRunner
from axonx.task.storage import artifact_record, read_metadata


@pytest.mark.parametrize("state", [None, "queued", "running", "failed", "cancelled", "unknown"])
def test_research_metadata_rejects_unsuccessful_or_missing_state(tmp_path, state):
    path = tmp_path / "metadata.json"
    value = {
        "version": 1,
        "task_type": "etl",
        "output_params": {"artifacts": {"dataset": {"path": "dataset.parquet"}}},
    }
    if state is not None:
        value["state"] = state
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="Upstream Task must have succeeded"):
        read_metadata(path)


@pytest.mark.parametrize("exit_code", [0, 1])
def test_backtest_accepts_artifact_only_after_successful_upstream_run(tmp_path, exit_code):
    class Predict(BaseTask):
        task_type = TaskType.PREDICT

        def build_task_steps(self):
            yield self.write_predictions

        def write_predictions(self):
            (self.task_dir / "predictions.parquet").write_bytes(b"artifact fixture")

        def build_output_params(self):
            return BaseOutputParams(
                artifacts={"predictions": artifact_record(self.task_dir / "predictions.parquet", self.task_dir)}
            )

        @staticmethod
        def exit_code(_output):
            return exit_code

    source = Predict({}, workspace_path=tmp_path, reg_name="predict")
    status = TaskRunner().run(source)
    consumer = BaseStockBacktestTask({}, workspace_path=tmp_path, reg_name="backtest")
    assert status.output_params["artifacts"]["predictions"]
    if exit_code:
        assert status.state == TaskState.FAILED
        with pytest.raises(ValueError, match="Upstream Task must have succeeded"):
            consumer.source_file(source.task_id, "predictions")
    else:
        path, metadata = consumer.source_file(source.task_id, "predictions")
        assert path.is_relative_to(consumer.task_dir)
        assert path.read_bytes() == (source.task_dir / "predictions.parquet").read_bytes()
        assert metadata["state"] == TaskState.SUCCEEDED.value
