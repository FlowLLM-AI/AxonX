"""Runner cleanup and business failure hooks preserve the primary failure."""

import pytest

from axonx.task.core import BaseOutputParams, BaseTask
from axonx.task.runtime.runner import TaskRunner


class ResourceTask(BaseTask):
    def __init__(self, *args, failure=None, cleanup_failure=False, output_failure=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.failure = failure
        self.cleanup_failure = cleanup_failure
        self.output_failure = output_failure
        self.events = []

    def build_task_steps(self):
        yield self.work

    def work(self):
        self.events.append("work")
        if self.failure:
            raise self.failure

    def close(self):
        self.events.append("close")
        if self.cleanup_failure:
            raise RuntimeError("cleanup failed")

    def on_failure(self, error):
        self.events.append(str(error))

    def build_output_params(self):
        self.events.append("output")
        if self.output_failure:
            raise ValueError("output failed")
        return BaseOutputParams()


def test_resources_close_before_success_output(tmp_path):
    task = ResourceTask({}, workspace_path=tmp_path, reg_name="resource")
    assert TaskRunner().run(task).exit_code == 0
    assert task.events == ["work", "close", "output"]


@pytest.mark.parametrize("cleanup_failure", [False, True])
def test_cleanup_preserves_step_failure_and_invokes_failure_hook(tmp_path, cleanup_failure):
    task = ResourceTask(
        {},
        workspace_path=tmp_path,
        reg_name="resource",
        failure=ValueError("step failed"),
        cleanup_failure=cleanup_failure,
    )
    with pytest.raises(ValueError, match="step failed"):
        TaskRunner().run(task)
    assert task.events == ["work", "close", "step failed"]


def test_output_failure_invokes_failure_hook_after_cleanup(tmp_path):
    task = ResourceTask({}, workspace_path=tmp_path, reg_name="resource", output_failure=True)
    with pytest.raises(ValueError, match="output failed"):
        TaskRunner().run(task)
    assert task.events == ["work", "close", "output", "output failed"]
