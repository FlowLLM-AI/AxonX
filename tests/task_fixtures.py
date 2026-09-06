"""Importable task fixtures used by process-isolation tests."""

# Test fixtures favor descriptive names over repeated docstrings.
# pylint: disable=missing-class-docstring,missing-function-docstring

import os
import time
from pathlib import Path
from axonx.task import BaseTask, BaseConfig


class Config(BaseConfig):
    delay: float = 0
    fail: bool = False
    marker: str = ""


class ProbeTask(BaseTask):
    config: Config
    output_keys = ("pid", "value")

    def build_task_steps(self):
        yield self.first
        assert self.context["value"] == 1  # verifies lazy generator consumption
        yield self.second

    def first(self):
        if self.config.marker:
            Path(self.config.marker).write_text(str(os.getpid()), encoding="utf-8")
        print("worker started", flush=True)
        time.sleep(self.config.delay)
        if self.config.fail:
            raise ValueError("intentional failure")
        self.context.update(value=1, pid=os.getpid())

    def second(self):
        self.context["value"] += 1
