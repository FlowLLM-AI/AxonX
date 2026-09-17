"""Command-line parsing and execution tests."""

# Tests favor descriptive class and function names over repeated docstrings.
# pylint: disable=missing-class-docstring,missing-function-docstring

import inspect
import json
import threading
from pathlib import Path
from time import monotonic
from types import SimpleNamespace

import pandas as pd
import pytest
from pydantic import ValidationError

from axonx import BaseInputParams, BaseOutputParams, BaseTask, cli
from axonx.components.client import HttpClient
from axonx.constants import AXONX_SERVICE_INFO, AXONX_TASK_STATUS_MIN_INTERVAL
from axonx.enums import TaskType
from axonx.schema import ClientOptions, Command, Response, TaskStatus
from axonx.task.common import DemoTask
from axonx.task.core import (
    BacktestTask,
    BaseAnalysisTask,
    BaseETLTask,
    BasePredictTask,
    BaseTrainTask,
)
from axonx.task.data import DownloadTushareTask, TushareDownloadInputParams
from axonx.task.executor import TaskCommandExecutor
from axonx.task.resolver import list_installed_task_infos
from axonx.task.status_reporter import (
    HttpTaskStatusReporter,
    create_task_status_reporter,
)
from axonx.utils import get_logger
from axonx.utils.cli import parse_command


class CliInputParams(BaseInputParams):
    amount: int
    dry_run: bool = False


class CliOutputParams(BaseOutputParams):
    amount: int
    dry_run: bool


class CliTask(BaseTask):
    """Expose a minimal configurable Task for command-line execution tests."""

    task_type = TaskType.ANALYSIS
    input_cls = CliInputParams
    output_cls = CliOutputParams

    def build_task_steps(self):
        yield self.record_config

    def record_config(self):
        self.report_progress(50)
        self.context.update(amount=self.input_params.amount, dry_run=self.input_params.dry_run)

    def build_output_params(self) -> CliOutputParams:
        return CliOutputParams(amount=self.context["amount"], dry_run=self.context["dry_run"])


def test_task_status_records_the_active_process_log(tmp_path):
    get_logger(log_dir=tmp_path / "logs", log_to_console=False, force_init=True)
    try:
        task = CliTask({"amount": 1}, workspace_path=tmp_path, reg_name="sample")
        assert Path(task.status.log_path).parent == (tmp_path / "logs").resolve()
    finally:
        get_logger(log_to_console=False, log_to_file=False, force_init=True)


def test_installed_task_infos_include_only_public_config(monkeypatch):
    monkeypatch.setattr(
        "axonx.task.resolver.installed_tasks",
        lambda: {"sample": CliTask},
    )

    info = list_installed_task_infos()[0]

    assert info.name == "sample"
    assert info.source == "plugin"
    assert info.task_type == TaskType.ANALYSIS
    assert set(info.output_schema["properties"]) == {"artifacts", "amount", "dry_run"}
    assert set(info.config_schema["properties"]) == {"amount", "dry_run", "task_name", "include_time"}
    assert info.config_schema["required"] == ["amount"]


def test_etl_catalog_exposes_domain_input_and_output_contracts():
    info = next(item for item in list_installed_task_infos() if item.name == "alpha158_etl")
    assert "input_dir" in info.config_schema["required"]
    assert {"metadata_file", "output_file", "rows", "date_range"} <= set(info.output_schema["properties"])
    assert {"metadata_file", "output_file", "rows", "date_range"} <= set(info.output_schema["required"])


def test_domain_task_bases_remain_abstract():
    for task_cls in (BaseETLTask, BaseAnalysisTask, BaseTrainTask, BasePredictTask):
        assert inspect.isabstract(task_cls)
        assert {"build_task_steps", "build_output_params"} <= task_cls.__abstractmethods__


def test_builtin_task_types_come_from_their_configs(tmp_path):
    demo = DemoTask({"x": 1, "y": 2}, workspace_path=tmp_path)
    download = DownloadTushareTask({}, workspace_path=tmp_path)

    assert demo.task_id.startswith("demo#")
    assert demo.status.task_type == TaskType.BASE
    assert download.task_id.startswith("download_tushare_task#")
    assert download.status.task_type == TaskType.API
    assert "task_type" not in demo.status.config

    with pytest.raises(ValidationError, match="extra_forbidden"):
        CliInputParams(amount=1, task_type=TaskType.ETL)


def test_installed_task_infos_require_an_explicit_class_docstring(monkeypatch):
    class UndocumentedTask(CliTask):
        __doc__ = None

    monkeypatch.setattr(
        "axonx.task.resolver.installed_tasks",
        lambda: {"undocumented": UndocumentedTask},
    )

    with pytest.raises(TypeError, match="must define a detailed class docstring"):
        list_installed_task_infos()


@pytest.fixture(autouse=True)
def isolate_dotenv_loading(monkeypatch):
    monkeypatch.setattr(cli, "load_env", lambda **_kwargs: {})


def test_tushare_config_accepts_compact_dates_converted_by_cli():
    command, _ = parse_command(
        [
            "exec",
            "--task",
            "download_tushare_task",
            "--end-date",
            "20260912",
        ],
    )

    config = TushareDownloadInputParams.model_validate(
        {key: value for key, value in command.arguments.items() if key == "end_date"},
    )

    assert config.end_date == "20260912"


def test_tushare_config_uses_explicit_start_date(tmp_path):
    task = DownloadTushareTask(
        {"start_date": 20100101, "end_date": 20260914, "datasets": "stk_limit"},
        workspace_path=tmp_path,
    )

    task.initialize()

    assert task.context["start_date"] == "20100101"
    assert task.context["end_date"] == "20260914"
    assert len(task.context["days"]) == 6101


def test_tushare_config_rejects_reversed_explicit_range(tmp_path):
    task = DownloadTushareTask(
        {"start_date": "20260915", "end_date": "20260914"},
        workspace_path=tmp_path,
    )

    with pytest.raises(ValueError, match="start_date 不能晚于 end_date"):
        task.initialize()


def test_tushare_download_directory_is_inside_workspace(tmp_path):
    task = DownloadTushareTask(
        {"end_date": "20260912"},
        workspace_path=tmp_path,
    )

    task.initialize()

    assert task.context["root"] == tmp_path / "tushare"
    assert task.context["start_date"] == "20260906"
    assert task.context["end_date"] == "20260912"


def test_tushare_download_reports_once_per_hundred_items(monkeypatch, tmp_path):
    task = DownloadTushareTask(
        {"end_date": "20260720", "days_back": 201},
        workspace_path=tmp_path,
    )
    monkeypatch.setattr(task, "_query", lambda *_args, **_kwargs: pd.DataFrame())
    monkeypatch.setattr(task, "download_hs300_weight", lambda _start, _end: None)
    snapshots = []

    task.execute(emit=snapshots.append)

    assert [step.name for step in task.status.steps] == [
        "initialize",
        "download_static",
        "download_stk_limits",
        "download_daily",
        "download_adj_factors",
        "download_hs300_weights",
        "sort_output_files",
    ]
    market_progress = [
        status.steps[3].percentage
        for status in snapshots
        if len(status.steps) == 4 and status.steps[3].percentage is not None
    ]
    assert market_progress == pytest.approx([100 / 201 * 100, 200 / 201 * 100, 100])


def test_tushare_download_groups_are_independently_selectable(tmp_path):
    static_task = DownloadTushareTask({"datasets": "static"}, workspace_path=tmp_path)
    limit_task = DownloadTushareTask({"datasets": "stk_limit"}, workspace_path=tmp_path)

    assert [step.__name__ for step in static_task.build_task_steps()] == [
        "initialize",
        "download_static",
        "sort_output_files",
    ]
    assert [step.__name__ for step in limit_task.build_task_steps()] == [
        "initialize",
        "download_stk_limits",
        "sort_output_files",
    ]


def test_tushare_download_files_are_sorted_by_date_and_dataset(tmp_path):
    task = DownloadTushareTask(
        {"end_date": "20260101", "days_back": 1},
        workspace_path=tmp_path,
    )
    task.initialize()
    root = task.context["root"]
    task.context["files"] = [
        str(root / "2026" / "20260105" / "index_weight.parquet"),
        str(root / "2026" / "20260104" / "adj_factor.parquet"),
        str(root / "2026" / "20260105" / "adj_factor.parquet"),
        str(root / "2026" / "20260104" / "daily.parquet"),
        str(root / "2026" / "20260105" / "daily.parquet"),
    ]

    task.sort_output_files()

    assert [path.relative_to(root).as_posix() for path in map(Path, task.context["files"])] == [
        "2026/20260104/daily.parquet",
        "2026/20260104/adj_factor.parquet",
        "2026/20260105/daily.parquet",
        "2026/20260105/adj_factor.parquet",
        "2026/20260105/index_weight.parquet",
    ]


def test_backtest_paths_are_resolved_from_prediction_task_id(tmp_path):
    prediction_dir = tmp_path / "predict" / "predict#example"
    prediction_dir.mkdir(parents=True)
    (prediction_dir / "metadata.json").write_text(
        json.dumps(
            {
                "output_params": {
                    "protocol": {"actual_return_unit": "decimal"},
                    "artifacts": {"predictions": {"path": "predictions.parquet"}},
                },
            },
        ),
        encoding="utf-8",
    )
    task = BacktestTask({"prediction_task_id": "predict#example"}, workspace_path=tmp_path)

    task.resolve_prediction_task()

    assert task.context["predictions_path"] == prediction_dir / "predictions.parquet"
    assert task.context["output_dir"] == tmp_path / "backtest" / task.task_id
    assert task.context["daily_path"] == task.context["output_dir"] / "daily.parquet"
    assert task.context["summary_path"] == task.context["output_dir"] / "summary.parquet"


def test_task_id_is_generated_internally_and_read_only():
    task = DemoTask({"x": 1, "y": 2, "task_name": "fixed"}, workspace_path=".")
    assert task.task_id.startswith("demo#fixed#")
    assert len(task.task_id.split("#")[2]) == 14
    assert task.task_metadata is None
    task.execute()
    assert task.task_metadata.task_id == task.task_id
    assert task.task_metadata.input_params is task.input_params
    assert "task_id" not in task.input_params.model_dump()


def test_task_id_can_omit_time_and_defaults_to_eight_uuid_characters():
    named = DemoTask({"x": 1, "y": 2, "task_name": "experiment-1", "include_time": False}, workspace_path=".")
    assert named.task_id == "demo#experiment-1"
    replacement = DemoTask({"x": 3, "y": 4, "task_name": "experiment-1", "include_time": False}, workspace_path=".")
    assert replacement.task_id == named.task_id
    assert named.execute()["result"] == 3
    assert replacement.execute()["result"] == 7

    generated = DemoTask({"x": 1, "y": 2, "include_time": False}, workspace_path=".")
    assert len(generated.input_params.task_name) == 8
    assert generated.task_id == f"demo#{generated.input_params.task_name}"

    with pytest.raises(ValidationError):
        BaseInputParams(task_name="invalid#name")


def test_task_status_accepts_an_optional_log_path():
    status = TaskStatus(
        task_id="analysis#example",
        task_type=TaskType.ANALYSIS,
        log_path="logs/example.log",
    )

    assert status.log_path == "logs/example.log"
    assert status.model_dump(mode="json")["log_path"] == "logs/example.log"


def test_local_task_uses_registered_config(monkeypatch, capsys):
    monkeypatch.setattr("axonx.task.executor.resolve_task", lambda _name: CliTask)

    assert cli.main(["exec", "--task", "sample", "--amount", "3", "--dry-run", "true"]) == 0

    assert json.loads(capsys.readouterr().out) == {"artifacts": {}, "amount": 3, "dry_run": True}


def test_task_status_keeps_effective_config_for_reruns(monkeypatch, tmp_path):
    monkeypatch.setattr("axonx.task.executor.resolve_task", lambda _name: CliTask)
    command, _ = parse_command(["exec", "--task", "sample", "--amount", "3"])

    execution = TaskCommandExecutor(tmp_path).execute(command)

    assert execution.status.task_name == "sample"
    assert execution.status.config == {
        "amount": 3,
        "dry_run": False,
        "task_name": execution.status.task_id.split("#")[1],
        "include_time": True,
    }
    assert "task_id" not in execution.status.config
    assert "task_type" not in execution.status.config


def test_exec_passes_application_workspace_to_task(monkeypatch, capsys, tmp_path):
    class WorkspaceInputParams(BaseInputParams):
        pass

    class WorkspaceOutputParams(BaseOutputParams):
        workspace_path: Path

    class WorkspaceTask(BaseTask):
        task_type = TaskType.ANALYSIS
        input_cls = WorkspaceInputParams
        output_cls = WorkspaceOutputParams

        def build_task_steps(self):
            return ()

        def build_output_params(self) -> WorkspaceOutputParams:
            return WorkspaceOutputParams(workspace_path=self.workspace_path)

    monkeypatch.setattr("axonx.task.executor.resolve_task", lambda _name: WorkspaceTask)
    monkeypatch.setattr(
        cli,
        "resolve_app_config",
        lambda **_kwargs: {"workspace_dir": str(tmp_path)},
    )

    assert cli.main(["exec", "--task", "sample"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "artifacts": {},
        "workspace_path": str(tmp_path.resolve()),
    }


def test_exec_loads_dotenv_without_overriding_injected_environment(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(cli, "load_env", lambda **kwargs: calls.append(kwargs) or {})
    monkeypatch.setattr("axonx.task.executor.installed_tasks", lambda: {})

    assert cli.main(["exec"]) == 0
    assert calls == [{"override": False}]
    assert capsys.readouterr().out == ""


def test_progress_delivery_runs_on_a_dedicated_thread(monkeypatch):
    caller = threading.get_ident()
    deliveries = []

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def set_status(self, status):
            deliveries.append((threading.get_ident(), status))

    monkeypatch.setattr("axonx.task.status_reporter.HttpClient", Client)
    task = CliTask({"amount": 1}, workspace_path=".", reg_name="sample")
    with HttpTaskStatusReporter(task.logger, min_interval=0) as reporter:
        task.execute(emit=reporter.publish)

    percentages = [status.steps[0].percentage if status.steps else None for _, status in deliveries]
    assert percentages == [None, None, None, 50, 100, 100]
    assert deliveries[0][1].steps == []
    assert deliveries[-1][1].steps[0].finished_at is not None
    assert deliveries[-1][1].state == "succeeded"
    assert all(thread_id != caller for thread_id, _ in deliveries)


def test_progress_delivery_coalesces_queued_updates(monkeypatch):
    release = threading.Event()
    deliveries = []

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def set_status(self, status):
            if not deliveries:
                release.wait(timeout=5)
            deliveries.append(status)

    class BurstTask(CliTask):
        def record_config(self):
            for percentage in (10, 20, 30):
                self.report_progress(percentage)
            self.context.update(amount=self.input_params.amount, dry_run=self.input_params.dry_run)

    monkeypatch.setattr("axonx.task.status_reporter.HttpClient", Client)
    task = BurstTask({"amount": 1}, workspace_path=".", reg_name="burst")
    with HttpTaskStatusReporter(task.logger, min_interval=0) as reporter:
        task.execute(emit=reporter.publish)
        release.set()

    percentages = [
        status.steps[-1].percentage for status in deliveries if status.steps and status.steps[-1].finished_at is None
    ]
    assert percentages == [None, 30]
    assert deliveries[-1].state == "succeeded"


def test_progress_delivery_observes_minimum_interval(monkeypatch):
    deliveries = []

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def set_status(self, status):
            deliveries.append((monotonic(), status))

    monkeypatch.setattr("axonx.task.status_reporter.HttpClient", Client)
    task = CliTask({"amount": 1}, workspace_path=".", reg_name="sample")
    with HttpTaskStatusReporter(task.logger, min_interval=0.05) as reporter:
        task.execute(emit=reporter.publish)

    assert len(deliveries) > 1
    intervals = [current[0] - previous[0] for previous, current in zip(deliveries, deliveries[1:])]
    assert min(intervals) >= 0.04


def test_status_reporter_interval_is_configurable_from_environment(monkeypatch):
    monkeypatch.setenv(AXONX_SERVICE_INFO, '{"host":"localhost","port":1024}')
    monkeypatch.setenv(AXONX_TASK_STATUS_MIN_INTERVAL, "1.25")

    task = CliTask({"amount": 1}, workspace_path=".", reg_name="sample")
    reporter = create_task_status_reporter(task.logger)

    assert isinstance(reporter, HttpTaskStatusReporter)
    assert reporter._min_interval == 1.25  # pylint: disable=protected-access


def test_status_reporter_invalid_interval_uses_default(monkeypatch, capsys):
    monkeypatch.setenv(AXONX_SERVICE_INFO, '{"host":"localhost","port":1024}')
    monkeypatch.setenv(AXONX_TASK_STATUS_MIN_INTERVAL, "invalid")

    task = CliTask({"amount": 1}, workspace_path=".", reg_name="sample")
    reporter = create_task_status_reporter(task.logger)

    assert isinstance(reporter, HttpTaskStatusReporter)
    assert reporter._min_interval == 3  # pylint: disable=protected-access
    assert "using 3 seconds" in capsys.readouterr().err


def test_task_rejects_async_steps():
    class AsyncTask(CliTask):
        async def async_step(self):
            pass

        def build_task_steps(self):
            yield self.async_step

    task = AsyncTask({"amount": 1}, workspace_path=".", reg_name="async")
    with pytest.raises(TypeError, match="must be synchronous"):
        task.execute()
    assert task.status.state == "failed"


def test_task_steps_stay_on_the_calling_thread():
    caller = threading.get_ident()

    class ThreadTask(CliTask):
        class ThreadOutputParams(BaseOutputParams):
            thread_id: int

        output_cls = ThreadOutputParams

        def record_config(self):
            self.context["thread_id"] = threading.get_ident()

        def build_output_params(self) -> ThreadOutputParams:
            return self.ThreadOutputParams(thread_id=self.context["thread_id"])

    assert ThreadTask({"amount": 1}, workspace_path=".", reg_name="thread").execute() == {
        "artifacts": {},
        "thread_id": caller,
    }


def test_demo_task_exercises_dynamic_steps_and_outputs():
    equal = DemoTask({"x": 2, "y": 2}, workspace_path=".")
    assert equal.execute() == {"artifacts": {}, "result": 4, "branch": "equal", "operands": ["x", "y"]}
    assert [step.name for step in equal.status.steps] == [
        "initialize",
        "add_equal_operands",
        "finish",
    ]

    different = DemoTask({"x": 2, "y": 3}, workspace_path=".")
    different.execute()
    assert [step.name for step in different.status.steps] == [
        "initialize",
        "add_x",
        "add_y",
        "finish",
    ]
    assert different.status.state == "succeeded"
    assert different.status.exit_code == 0
    assert different.status.error == ""


def test_demo_task_exercises_failure_status():
    task = DemoTask({"x": 1, "y": 2, "fail": True}, workspace_path=".")
    with pytest.raises(RuntimeError, match="Demo failure requested"):
        task.execute()
    assert task.status.state == "failed"
    assert task.status.error == "RuntimeError: Demo failure requested"
    assert task.status.steps[-1].name == "fail"
    assert task.status.steps[-1].percentage == 50


def test_submit_forwards_the_same_task_arguments(monkeypatch, capsys):
    calls = []

    class Client:
        def __init__(self, **options):
            calls.append(("client", options))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def run_job(self, name, **arguments):
            calls.append((name, arguments))
            return Response(answer={"task_id": "analysis_20240601120000_abcd"})

    monkeypatch.setattr(cli, "HttpClient", Client)

    status = cli.main(
        [
            "--host-ip",
            "service",
            "--host-port",
            "9000",
            "--timeout",
            "5",
            "submit",
            "--task",
            "sample",
            "--amount",
            "3",
            "--dry-run",
            "true",
        ],
    )

    assert status == 0
    assert calls == [
        ("client", {"host_ip": "service", "host_port": 9000, "timeout": 5}),
        (
            "submit",
            {
                "task": "sample",
                "amount": 3,
                "dry_run": True,
                "_axonx_argv": [
                    "--task",
                    "sample",
                    "--amount",
                    "3",
                    "--dry-run",
                    "true",
                ],
            },
        ),
    ]
    assert json.loads(capsys.readouterr().out)["answer"] == {
        "task_id": "analysis_20240601120000_abcd",
    }


def test_start_prints_logo_before_running_service(monkeypatch):
    events = []
    app = SimpleNamespace(app_config=SimpleNamespace(service=None, enable_logo=True))

    class Service:
        def run_app(self, received_app):
            assert received_app is app
            events.append("serve")

    service = Service()
    configs = []
    monkeypatch.setattr(
        cli,
        "load_env",
        lambda: {"FROM_DOTENV": "dotenv", "PRECEDENCE": "dotenv"},
    )
    monkeypatch.setattr(
        cli,
        "resolve_app_config",
        lambda **_kwargs: {"environment": {"PRECEDENCE": "config"}},
    )
    monkeypatch.setattr(
        cli,
        "Application",
        lambda **config: configs.append(config) or app,
    )
    monkeypatch.setattr(cli, "HttpService", lambda **_config: service)
    monkeypatch.setattr(
        cli,
        "print_logo",
        lambda config, runtime: events.append((config, runtime)),
    )

    assert cli.main(["start"]) == 0
    assert configs == [
        {"environment": {"FROM_DOTENV": "dotenv", "PRECEDENCE": "config"}},
    ]
    assert events == [(app.app_config, service), "serve"]


def test_exec_without_arguments_lists_available_tasks(monkeypatch, capsys):
    monkeypatch.setattr(
        "axonx.task.executor.installed_tasks",
        lambda: {"sample": CliTask},
    )

    assert cli.main(["exec"]) == 0

    assert capsys.readouterr().out == f"sample\t{__name__}.CliTask\n"


def test_exec_discovers_installed_plugin(capsys):
    assert cli.main(["exec"]) == 0
    assert "alpha158_etl\taxonx_alpha158.etl.Alpha158Task" in capsys.readouterr().out


def test_task_options_are_strict(monkeypatch, capsys):
    monkeypatch.setattr("axonx.task.executor.resolve_task", lambda _name: CliTask)

    assert cli.main(["exec", "--task", "sample", "--amount"]) == 2
    assert "pairs like --field value" in capsys.readouterr().err


def test_command_options_support_nested_fields():
    command, _ = parse_command(
        ["deploy", "--service.port", "2333", "--service.public-host", "example.test"],
    )

    assert command.arguments == {
        "service": {"port": 2333, "public_host": "example.test"},
        "_axonx_argv": [
            "--service.port",
            "2333",
            "--service.public-host",
            "example.test",
        ],
    }


def test_remote_ip_is_routing_metadata_not_a_task_argument():
    command, _ = parse_command(
        ["submit", "--task", "sample", "--remote-ip", "192.168.1.10", "--amount", "3"],
    )

    assert command.arguments == {
        "task": "sample",
        "remote_ip": "192.168.1.10",
        "amount": 3,
        "_axonx_argv": ["--task", "sample", "--amount", "3"],
    }


def test_passthrough_command_preserves_unparsed_arguments():
    command, _ = parse_command(["plugin", "build", "--output", "dist"])

    assert command.arguments == {"_axonx_argv": ["build", "--output", "dist"]}


def test_nested_options_reject_scalar_conflicts(capsys):
    assert cli.main(["start", "--service", "null", "--service.port", "2333"]) == 2
    assert "already a value" in capsys.readouterr().err


def test_command_uses_validated_http_client_options():
    command, client_options = parse_command(
        [
            "--host-ip",
            "service.internal",
            "--host-port",
            "4321",
            "--timeout",
            "5",
            "status",
        ],
    )

    assert isinstance(command, Command)
    assert isinstance(client_options, ClientOptions)
    assert client_options.host_ip == "service.internal"
    assert client_options.host_port == 4321
    assert client_options.timeout == 5

    with pytest.raises(ValidationError):
        ClientOptions(timeout=True)
    with pytest.raises(ValidationError):
        HttpClient(host_ip="service.internal")


def test_client_option_names_are_still_valid_actions():
    command, _ = parse_command(["timeout"])

    assert command.action == "timeout"
