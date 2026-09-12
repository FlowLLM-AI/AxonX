"""Command-line parsing and execution tests."""

# Tests favor descriptive class and function names over repeated docstrings.
# pylint: disable=missing-class-docstring,missing-function-docstring

import json
from types import SimpleNamespace
import threading

import pytest
from pydantic import ValidationError

from axonx import cli
from axonx.components.client import HttpClient
from axonx.enumeration import TaskType
from axonx.schema import ClientOptions, Command, Response, TaskStatus
from axonx.task import BaseConfig, BaseTask
from axonx.task.backtest import RankingBacktestTask
from axonx.task.common import DemoTask
from axonx.task.data import DownloadTusharTask, TushareDownloadConfig
from axonx.task.task_status_reporter import HttpTaskStatusReporter
from axonx.utils.cli_utils import parse_command


class CliConfig(BaseConfig):
    amount: int
    dry_run: bool = False


class CliTask(BaseTask):
    config_cls = CliConfig
    task_type = TaskType.ANALYSIS
    output_keys = ("amount", "dry_run")

    def build_task_steps(self):
        yield self.record_config

    def record_config(self):
        self.report_progress(50)
        self.context.update(amount=self.config.amount, dry_run=self.config.dry_run)


@pytest.fixture(autouse=True)
def isolate_dotenv_loading(monkeypatch):
    monkeypatch.setattr(cli, "load_env", lambda **_kwargs: {})


def test_tushare_config_accepts_compact_dates_converted_by_cli():
    command, _ = parse_command(
        ["exec", "--task", "download_tushar_task", "--start-date", "20100101", "--end-date", "20260912"],
    )

    config = TushareDownloadConfig.model_validate(
        {key: value for key, value in command.arguments.items() if key in {"start_date", "end_date"}},
    )

    assert config.start_date == "20100101"
    assert config.end_date == "20260912"


def test_tushare_download_directory_is_inside_workspace(tmp_path):
    task = DownloadTusharTask(
        {"start_date": "20260912", "end_date": "20260912"},
        workspace_path=tmp_path,
    )

    task.initialize()

    assert task.context["root"] == tmp_path / "tushare"


def test_tushare_download_reports_once_per_hundred_items(monkeypatch, tmp_path):
    task = DownloadTusharTask(
        {"start_date": "20260101", "end_date": "20260720"},
        workspace_path=tmp_path,
    )
    monkeypatch.setattr(task, "download_market_day", lambda _day: None)
    monkeypatch.setattr(task, "download_hs300_weight", lambda _start, _end: None)
    snapshots = []

    task.execute(emit=snapshots.append)

    assert [step.name for step in task.status.steps] == [
        "initialize",
        "download_market_days",
        "download_hs300_weights",
    ]
    market_progress = [
        status.steps[1].percentage
        for status in snapshots
        if len(status.steps) == 2 and status.steps[1].percentage is not None
    ]
    assert market_progress == pytest.approx([100 / 201 * 100, 200 / 201 * 100, 100])


def test_backtest_relative_paths_are_resolved_from_workspace(tmp_path):
    task = RankingBacktestTask(
        {"input_file": "predictions/input.parquet", "output_dir": "backtests/example"},
        workspace_path=tmp_path,
    )

    task.resolve_paths()

    assert task.context["input_file"] == tmp_path / "predictions/input.parquet"
    assert task.context["output_dir"] == tmp_path / "backtests/example"
    assert task.context["daily_path"] == tmp_path / "backtests/example/daily.parquet"


def test_task_id_is_generated_internally_and_read_only():
    config = BaseConfig(task_id_suffix="fixed")

    task_id = config.generate_task_id(TaskType.ANALYSIS)

    assert task_id.startswith("analysis#")
    assert task_id.endswith("#fixed")
    assert config.task_id == task_id
    assert config.task_type == TaskType.ANALYSIS
    assert config.model_dump()["task_id"] == task_id
    assert config.model_dump(mode="json")["task_type"] == "analysis"
    assert config.generate_task_id(TaskType.ANALYSIS) == task_id
    with pytest.raises(ValueError, match="Task type mismatch"):
        config.generate_task_id(TaskType.ETL)
    with pytest.raises(ValueError, match="incomplete identity"):
        BaseConfig(task_id="incomplete").generate_task_id(TaskType.ANALYSIS)
    with pytest.raises(ValidationError, match="frozen"):
        config.task_id = "replacement"
    with pytest.raises(ValidationError, match="frozen"):
        config.task_type = TaskType.ETL


def test_task_status_accepts_an_optional_log_path():
    status = TaskStatus(task_id="analysis#example", task_type=TaskType.ANALYSIS, log_path="logs/example.log")

    assert status.log_path == "logs/example.log"
    assert status.model_dump(mode="json")["log_path"] == "logs/example.log"


def test_local_task_uses_registered_config(monkeypatch, capsys):
    monkeypatch.setattr("axonx.task.task_command_executor.resolve_task", lambda _name: CliTask)

    assert cli.main(["exec", "--task", "sample", "--amount", "3", "--dry-run", "true"]) == 0

    assert json.loads(capsys.readouterr().out) == {"amount": 3, "dry_run": True}


def test_exec_passes_application_workspace_to_task(monkeypatch, capsys, tmp_path):
    class WorkspaceTask(BaseTask):
        task_type = TaskType.ANALYSIS
        output_keys = ("workspace_path",)

        def build_task_steps(self):
            return ()

    monkeypatch.setattr("axonx.task.task_command_executor.resolve_task", lambda _name: WorkspaceTask)
    monkeypatch.setattr(cli, "resolve_app_config", lambda **_kwargs: {"workspace_dir": str(tmp_path)})

    assert cli.main(["exec", "--task", "sample"]) == 0
    assert json.loads(capsys.readouterr().out) == {"workspace_path": str(tmp_path.resolve())}


def test_exec_loads_dotenv_without_overriding_injected_environment(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(cli, "load_env", lambda **kwargs: calls.append(kwargs) or {})
    monkeypatch.setattr("axonx.task.task_command_executor.installed_tasks", lambda: {})

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

    monkeypatch.setattr("axonx.task.task_status_reporter.HttpClient", Client)
    task = CliTask({"amount": 1}, workspace_path=".")
    with HttpTaskStatusReporter(task.logger) as reporter:
        task.execute(emit=reporter.publish)

    percentages = [status.steps[0].percentage if status.steps else None for _, status in deliveries]
    assert percentages == [None, None, None, 50, 100, 100]
    assert deliveries[0][1].steps == []
    assert deliveries[-1][1].steps[0].finished_at is not None
    assert deliveries[-1][1].state == "succeeded"
    assert all(thread_id != caller for thread_id, _ in deliveries)


def test_task_rejects_async_steps():
    class AsyncTask(CliTask):
        async def async_step(self):
            pass

        def build_task_steps(self):
            yield self.async_step

    task = AsyncTask({"amount": 1}, workspace_path=".")
    with pytest.raises(TypeError, match="must be synchronous"):
        task.execute()
    assert task.status.state == "failed"


def test_task_steps_stay_on_the_calling_thread():
    caller = threading.get_ident()

    class ThreadTask(CliTask):
        output_keys = ("thread_id",)

        def record_config(self):
            self.context["thread_id"] = threading.get_ident()

    assert ThreadTask({"amount": 1}, workspace_path=".").execute() == {"thread_id": caller}


def test_demo_task_exercises_dynamic_steps_and_outputs():
    equal = DemoTask({"x": 2, "y": 2}, workspace_path=".")
    assert equal.execute() == {"result": 4, "branch": "equal", "operands": ["x", "y"]}
    assert [step.name for step in equal.status.steps] == ["initialize", "add_equal_operands", "finish"]

    different = DemoTask({"x": 2, "y": 3}, workspace_path=".")
    different.execute()
    assert [step.name for step in different.status.steps] == ["initialize", "add_x", "add_y", "finish"]
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
                "_axonx_argv": ["--task", "sample", "--amount", "3", "--dry-run", "true"],
            },
        ),
    ]
    assert json.loads(capsys.readouterr().out)["answer"] == {"task_id": "analysis_20240601120000_abcd"}


def test_start_prints_logo_before_running_service(monkeypatch):
    events = []
    app = SimpleNamespace(app_config=SimpleNamespace(service=None, enable_logo=True))

    class Service:
        def run_app(self, received_app):
            assert received_app is app
            events.append("serve")

    service = Service()
    configs = []
    monkeypatch.setattr(cli, "load_env", lambda: {"FROM_DOTENV": "dotenv", "PRECEDENCE": "dotenv"})
    monkeypatch.setattr(
        cli,
        "resolve_app_config",
        lambda **_kwargs: {"environment": {"PRECEDENCE": "config"}},
    )
    monkeypatch.setattr(cli, "Application", lambda **config: configs.append(config) or app)
    monkeypatch.setattr(cli, "HttpService", lambda **_config: service)
    monkeypatch.setattr(cli, "print_logo", lambda config, runtime: events.append((config, runtime)))

    assert cli.main(["start"]) == 0
    assert configs == [{"environment": {"FROM_DOTENV": "dotenv", "PRECEDENCE": "config"}}]
    assert events == [(app.app_config, service), "serve"]


def test_exec_without_arguments_lists_available_tasks(monkeypatch, capsys):
    monkeypatch.setattr("axonx.task.task_command_executor.installed_tasks", lambda: {"sample": CliTask})

    assert cli.main(["exec"]) == 0

    assert capsys.readouterr().out == f"sample\t{__name__}.CliTask\n"


def test_exec_discovers_installed_plugin(capsys):
    assert cli.main(["exec"]) == 0
    assert "sales\taxonx_polars_demo.sales.SalesTask" in capsys.readouterr().out


def test_task_options_are_strict(monkeypatch, capsys):
    monkeypatch.setattr("axonx.task.task_command_executor.resolve_task", lambda _name: CliTask)

    assert cli.main(["exec", "--task", "sample", "--amount"]) == 2
    assert "pairs like --field value" in capsys.readouterr().err


def test_command_options_support_nested_fields():
    command, _ = parse_command(["deploy", "--service.port", "2333", "--service.public-host", "example.test"])

    assert command.arguments == {
        "service": {"port": 2333, "public_host": "example.test"},
        "_axonx_argv": ["--service.port", "2333", "--service.public-host", "example.test"],
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
        ["--host-ip", "service.internal", "--host-port", "4321", "--timeout", "5", "status"],
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
