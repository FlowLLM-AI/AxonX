"""Private worker protocol. Never construct an Application in a task process."""

import asyncio
import importlib
import json
import os
from pathlib import Path
import sys
import traceback

from ...constants import AXONX_SERVICE_INFO
from ...task import BaseTask
from ..client import HttpClient
from ..component_registry import R


def write_json(path, value):
    """Atomically write a JSON-serializable value to ``path``."""
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False))
    temporary.replace(path)


def progress_reporter(directory, request):
    """Build a callback that persists and optionally uploads task progress."""
    service_available = bool(os.environ.get(AXONX_SERVICE_INFO))
    task_steps = []

    def report(**event):
        step_index = event["step_index"]
        task_step = event["task_step"]
        if step_index == len(task_steps):
            task_steps.append(task_step)
        else:
            task_steps[step_index] = task_step
        write_json(directory / "progress.json", {"task_steps": task_steps})
        if not service_available:
            return
        try:

            async def upload():
                async with HttpClient(timeout=1) as client:
                    return await client.run_job(
                        "report_task_progress",
                        manager=request["manager"],
                        run_id=request["run_id"],
                        step_index=step_index,
                        task_step=task_step,
                    )

            response = asyncio.run(upload())
            if not response.success:
                print(f"Progress upload failed: {response.answer}", file=sys.stderr)
        except Exception as exc:
            print(
                f"Progress upload failed: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )

    return report


def main():
    """Execute the task request supplied on the command line."""
    directory = Path(sys.argv[1]).resolve().parent
    try:
        request = json.loads((directory / "request.json").read_text())
        module, name = request["target"].split(":", 1)
        with R.preserve(allow_mutation=True):
            cls = importlib.import_module(module)
            for part in name.split("."):
                cls = getattr(cls, part)
        if not isinstance(cls, type) or not issubclass(cls, BaseTask):
            raise TypeError("Worker target must subclass BaseTask")
        task = cls(request["config"])
        result = task.execute(
            emit=progress_reporter(directory, request),
            cancelled=(directory / "cancel").exists,
        )
        code = task.exit_code(result)
        write_json(directory / "result.json", {"output": result})
        return code
    except BaseException as exc:
        traceback.print_exc()
        write_json(directory / "result.json", {"error": f"{type(exc).__name__}: {exc}"})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
