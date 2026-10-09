"""Registration, parameter isolation and Qlib operator boundary regressions."""

import importlib
from pathlib import Path
import tomllib

import numpy as np
import polars as pl
import pytest
import yaml

from axonx_qlib_a158.internal.features import rolling_features, rolling_inputs
from axonx_qlib_a158.train import LgbmTrainInputParams

ROOT = Path(__file__).resolve().parents[2]


def test_new_plugin_contributions_resolve_without_old_aliases():
    project = tomllib.loads((ROOT / "plugins/qlib_a158/pyproject.toml").read_text())["project"]
    entries = project["entry-points"]
    assert entries["axonx.plugins"] == {"qlib_a158": "axonx_qlib_a158"}
    assert entries["axonx.configs"] == {"qlib_a158": "axonx_qlib_a158.config:qlib_a158_demo"}
    tasks = yaml.safe_load((ROOT / "plugins/qlib_a158/axonx_qlib_a158/plugin.yaml").read_text())["tasks"]
    assert set(tasks) == {f"qlib_a158_{stage}" for stage in ("etl", "factor", "train", "predict", "backtest")}
    for entry in tasks.values():
        module, name = entry.split(":")
        assert getattr(importlib.import_module(module), name).input_cls


def test_qlib_preset_preserves_lifecycle_and_explicit_overrides():
    source = {"parameter_preset": "qlib", "learning_rate": 0.04}
    current = LgbmTrainInputParams()
    reference = LgbmTrainInputParams(**source)
    assert source == {"parameter_preset": "qlib", "learning_rate": 0.04}
    assert reference.learning_rate == 0.04
    assert (reference.num_leaves, reference.max_depth) == (210, 8)
    assert reference.bagging_freq == 0
    assert reference.lambda_l1 == 205.6999
    assert reference.lambda_l2 == 580.9768
    for key in ("label_column", "trim_tail", "validation_ratio", "train_start", "train_end", "random_seed"):
        assert getattr(current, key) == getattr(reference, key)
    restored = LgbmTrainInputParams.model_validate(reference.model_dump())
    assert restored == reference
    with pytest.raises(ValueError):
        LgbmTrainInputParams(parameter_preset="unknown")


def panel(close, volume):
    return rolling_inputs(
        pl.DataFrame(
            {
                "ts_code": ["A"] * len(close),
                "_close": close,
                "_high": close,
                "_low": close,
                "_volume": volume,
                "_x": np.arange(len(close), dtype=float),
            }
        )
    )


def test_missing_quote_regression_keeps_day_offsets_and_pairs_the_denominator():
    close = [10.0, 12.0, None, 16.0, 18.0]
    result = rolling_features(panel(close, [100.0] * 5), 5).row(-1, named=True)
    observed = np.array([0, 1, 3, 4], dtype=float)
    slope, intercept = np.polyfit(observed, [10, 12, 16, 18], 1)
    assert result["BETA5"] == pytest.approx(slope / 18)
    assert result["RESI5"] == pytest.approx((18 - (slope * 4 + intercept)) / 18, abs=1e-10)
    assert result["RSQR5"] == pytest.approx(1.0)


def test_near_constant_windows_are_missing_like_qlib_correlation_guards():
    result = rolling_features(panel([10 + i * 1e-7 for i in range(5)], [100 + i * 1e-7 for i in range(5)]), 5)
    for name in ("CORR5", "CORD5", "RSQR5"):
        assert result[name][-1] is None


@pytest.mark.parametrize("labels", [["rank"], ["rank", "csz"]])
def test_parameter_comparison_runs_both_presets_with_one_etl(tmp_path, labels):
    from argparse import Namespace
    import json

    from test_stock_pipeline import raw_data
    from axonx.enums import TaskState
    from axonx.task.runtime.runner import TaskRunner
    from axonx_qlib_a158.etl import Alpha158Task
    from axonx_qlib_a158.scripts.compare_parameters import run_comparison

    dates = raw_data(tmp_path / "raw")
    workspace = tmp_path / "workspace"
    etl = Alpha158Task(
        {"input_dir": tmp_path / "raw", "start_date": dates[60]},
        workspace_path=workspace,
        reg_name="qlib_a158_etl",
    )
    assert TaskRunner().run(etl).state == TaskState.SUCCEEDED
    report = run_comparison(
        Namespace(
            workspace_path=workspace,
            etl_task=etl.task_id,
            train_start=dates[60],
            train_end=dates[75],
            pred_start=dates[75],
            pred_end=dates[-2],
            num_threads=1,
            num_boost_round=5,
            top_ns=[1, 3],
            transaction_cost_rate=0.002,
            labels=labels,
            buy_cost_rate=0.0005,
            sell_cost_rate=0.0015,
        )
    )
    expected = (
        {"axonx", "qlib"}
        if len(labels) == 1
        else {f"{label}_{preset}" for label in labels for preset in ["axonx", "qlib"]}
    )
    assert set(report["presets"]) == expected
    for entry in report["presets"].values():
        assert entry["parameters"]["bagging_freq"] == (1 if entry["parameter_preset"] == "axonx" else 0)
        assert entry["backtest_settings"]["buy_cost_rate"] == 0.0005
        assert entry["backtest_settings"]["sell_cost_rate"] == 0.0015
        assert entry["backtest_settings"]["as_of_date"] == dates[-2]
    saved = json.loads((Path(report["output_dir"]) / "comparison.json").read_text())
    assert saved["dataset_sha256"] == report["dataset_sha256"]
    summary = pl.read_csv(Path(report["output_dir"]) / "summary.csv")
    assert set(summary["preset"]) == {"axonx", "qlib"}
    assert set(summary["label"]) == set(labels)
    assert {"overall", "year"} <= set(summary["period_type"])


@pytest.mark.parametrize("value", ["20261301", "20260230", "invalid"])
def test_etl_date_boundaries_reject_invalid_calendar_dates(value):
    from axonx_qlib_a158.etl import Alpha158InputParams

    with pytest.raises(ValueError):
        Alpha158InputParams(start_date=value)


def test_side_fees_fail_clearly_with_an_unsupported_core(tmp_path, monkeypatch):
    from axonx_qlib_a158.backtest import Alpha158BacktestTask
    from axonx.task.builtins.stock.engine import BacktestConfig

    fields = {
        key: value
        for key, value in BacktestConfig.__dataclass_fields__.items()
        if key not in {"buy_cost_rate", "sell_cost_rate"}
    }
    monkeypatch.setattr(BacktestConfig, "__dataclass_fields__", fields)
    task = Alpha158BacktestTask({"buy_cost_rate": 0.0005}, workspace_path=tmp_path, reg_name="qlib_a158_backtest")
    with pytest.raises(RuntimeError, match="Separate buy/sell fees require AxonX core"):
        task.calculate()


@pytest.mark.parametrize("failed_wait", [False, True])
def test_pipeline_checks_selected_service_and_stops_on_failed_wait(tmp_path, failed_wait):
    import json
    import os
    import subprocess
    import sys

    command = tmp_path / "axonx"
    command.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "args = sys.argv[1:]\n"
        "assert os.getcwd() == os.environ['PIPELINE_CWD']\n"
        "with open(os.environ['PIPELINE_CALLS'], 'a') as output: output.write(json.dumps(args) + '\\n')\n"
        "if args[0] == 'get_task_definition': result = {'success': True, 'answer': {}}\n"
        "elif args[0] == 'submit':\n"
        "    result = {'success': True, 'answer': {'task_id': args[args.index('--task')+1], 'run_id': 'run'}}\n"
        "elif 'wait_task' in args:\n"
        "    state = 'failed' if os.environ.get('PIPELINE_FAIL') else 'succeeded'\n"
        "    result = {'success': True, 'answer': {'state': state}}\n"
        "else: raise SystemExit('Unexpected command')\n"
        "print(json.dumps(result))\n"
    )
    command.chmod(0o755)
    (tmp_path / "python3").symlink_to(sys.executable)
    log = tmp_path / "calls.jsonl"
    env = {
        **os.environ,
        "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
        "PIPELINE_CALLS": str(log),
        "PIPELINE_CWD": str(tmp_path),
    }
    if failed_wait:
        env["PIPELINE_FAIL"] = "1"
    else:
        env.pop("PIPELINE_FAIL", None)
    result = subprocess.run(
        ["bash", str(ROOT / "plugins/qlib_a158/axonx_qlib_a158/scripts/run_pipeline.sh")],
        env=env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert len([args for args in calls if args[0] == "get_task_definition"]) == 6
    submissions = [args for args in calls if args[0] == "submit"]
    assert result.returncode == (1 if failed_wait else 0)
    assert len(submissions) == (1 if failed_wait else 6)
    if not failed_wait:
        assert submissions[-1][-4:] == ["--buy-cost-rate", "0.0005", "--sell-cost-rate", "0.0015"]


@pytest.mark.parametrize("plugin", ["qlib_factor", "qlib_strategy"])
def test_extension_plugin_names_and_inherited_defaults(plugin):
    folder = ROOT / "plugins" / plugin
    package = f"axonx_{plugin}"
    project = tomllib.loads((folder / "pyproject.toml").read_text())["project"]
    assert project["name"] == "axonx-" + plugin.replace("_", "-")
    assert project["entry-points"]["axonx.plugins"] == {plugin: package}
    tasks = yaml.safe_load((folder / package / "plugin.yaml").read_text())["tasks"]
    assert set(tasks) == {f"{plugin}_{stage}" for stage in ["etl", "analysis", "train", "predict", "backtest"]}
    for entry in tasks.values():
        module, name = entry.split(":")
        assert getattr(importlib.import_module(module), name).input_cls
    from axonx_qlib_factor.train import LgbmTrainInputParams as FactorInput

    assert FactorInput().label_column == "label_return_rank"
    assert FactorInput().parameter_preset == "axonx"
    assert FactorInput(context_groups=None).context_groups == "none"
