"""Validate shipped plugin registrations, configurations and bilingual CLI examples."""

import re
import shlex
import tomllib
from pathlib import Path

import jsonschema
import pytest
from packaging.requirements import Requirement

from axonx.app.config.loader import ConfigLoader
from axonx.app.config.models import ApplicationConfig
from axonx.cli.parser import parse_command, parse_plugin_arguments
from axonx.plugin.manifest import PluginManifest
from axonx.task.runtime.catalog import TaskCatalog
from axonx.task.runtime.settings import ExecutionSettings

PLUGINS = Path(__file__).resolve().parents[2]
NAMES = ("qlib_a158", "qlib_factor", "qlib_strategy")
FENCES = re.compile(r"^```(?:bash|sh)\n(.*?)^```", re.MULTILINE | re.DOTALL)


def project(name):
    return tomllib.loads((PLUGINS / name / "pyproject.toml").read_text())


def task_catalog():
    registrations = []
    for name in NAMES:
        package = "axonx_" + name
        manifest = PluginManifest.parse((PLUGINS / name / package / "plugin.yaml").read_text(), name)
        registrations.extend((key, value, name) for key, value in manifest.tasks.items())
    return TaskCatalog(registrations)


def test_all_shipped_registrations_resolve_with_current_schemas():
    catalog = task_catalog()
    definitions = catalog.definitions()
    expected = {
        "qlib_a158_research",
        "qlib_a158_etl",
        "qlib_a158_analysis",
        "qlib_a158_compare",
        "qlib_a158_train",
        "qlib_a158_predict",
        "qlib_a158_portfolio",
        "qlib_a158_backtest",
        "qlib_factor_etl",
        "qlib_factor_train",
        "qlib_strategy_portfolio",
    }
    assert {definition.name for definition in definitions if definition.name.startswith("qlib_")} == expected
    for definition in definitions:
        jsonschema.Draft202012Validator.check_schema(definition.input_schema)
        jsonschema.Draft202012Validator.check_schema(definition.output_schema)


@pytest.mark.parametrize("name", NAMES)
def test_plugin_dependency_layers_require_current_contracts(name):
    config = project(name)
    requirements = {entry.name: entry for entry in map(Requirement, config["project"]["dependencies"])}
    dependencies = ["axonx"]
    if name != "qlib_a158":
        dependencies.append("axonx-qlib-a158")
    for dependency in dependencies:
        assert "0.3.0" in requirements[dependency].specifier
        assert "0.2.0" not in requirements[dependency].specifier


def test_plugins_register_distinct_implementations_without_application_presets():
    targets = []
    for name in NAMES:
        config = project(name)
        assert "axonx.configs" not in config["project"]["entry-points"]
        manifest = PluginManifest.parse((PLUGINS / name / ("axonx_" + name) / "plugin.yaml").read_text(), name)
        targets.extend(manifest.tasks.values())
    assert len(targets) == len(set(targets))
    strategy_dependencies = {Requirement(entry).name for entry in project("qlib_strategy")["project"]["dependencies"]}
    assert strategy_dependencies == {"axonx", "axonx-qlib-a158", "pydantic"}


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("readme", ["README.md", "README_ZH.md"])
def test_documented_plugin_commands_match_current_contracts(name, readme):
    catalog = task_catalog()
    jobs = ConfigLoader().load("default")["jobs"]
    documented_tasks = set()
    for body in FENCES.findall((PLUGINS / name / readme).read_text()):
        for line in body.replace("\\\n", " ").splitlines():
            if not line.strip().startswith("axonx "):
                continue
            for stage, task_type in [
                ("etl", "etl"),
                ("train", "train"),
                ("predict", "predict"),
                ("portfolio", "portfolio"),
            ]:
                line = line.replace(f"<{stage}_task_id>", f"{task_type}#qlib_a158_{stage}#example")
            command, _ = parse_command(shlex.split(line, comments=True)[1:])
            if command.action == "plugin":
                parse_plugin_arguments(command.raw_arguments)
            elif command.action == "exec":
                inputs = dict(command.arguments)
                registration = inputs.pop("task")
                documented_tasks.add(registration)
                task = catalog.resolve(registration)
                for key in ExecutionSettings.model_fields:
                    inputs.pop(key, None)
                task.input_cls.model_validate(inputs)
            elif command.action == "app":
                ApplicationConfig.model_validate(
                    {key: value for key, value in command.arguments.items() if key != "config"}
                )
            else:
                assert command.action in jobs
                jsonschema.validate(command.arguments, jobs[command.action].get("parameters", {}))
    manifest = PluginManifest.parse((PLUGINS / name / ("axonx_" + name) / "plugin.yaml").read_text(), name)
    assert set(manifest.tasks) <= documented_tasks


def test_feature_identity_tracks_semantics_and_order_without_workspace_details():
    from axonx.task.models.artifacts import task_protocol
    from axonx.task.models.identity import TaskType
    from axonx_qlib_a158.internal.modeling import feature_contract, feature_identity

    protocol = {
        **task_protocol(TaskType.ETL),
        "feature_family": "qlib_a158",
        "feature_columns": ["first", "second"],
        "trade_time": "1500",
        "return_unit": "decimal",
        "feature_rules": {"lookback_days": 60},
    }
    identity = feature_identity(protocol)
    enriched = {**protocol, "date_range": {"start": "20240101"}, "rows": 100, "source": "/another/workspace"}
    assert feature_identity(enriched) == identity
    assert feature_contract(enriched) == protocol
    for changes in (
        {"feature_columns": ["second", "first"]},
        {"feature_rules": {"lookback_days": 80}},
        {"feature_family": "qlib_factor"},
    ):
        assert feature_identity({**protocol, **changes}) != identity
    for columns in ([], ["first", "first"], [""], [1], "first"):
        with pytest.raises(ValueError, match="Feature columns"):
            feature_contract({**protocol, "feature_columns": columns})


def test_feature_matrix_preserves_order_and_maps_nonfinite_values_to_missing():
    import numpy as np
    import polars as pl

    from axonx_qlib_a158.internal.modeling import feature_matrix

    frame = pl.DataFrame(
        {
            "first": ["1", "bad", "inf", "NaN", None],
            "second": [2.0, float("nan"), float("inf"), -float("inf"), None],
            "flag": [True, False, None, True, False],
            "unused": ["ignored"] * 5,
        }
    )
    matrix = feature_matrix(frame, ("second", "flag", "first"))
    assert matrix.dtype == np.float64
    np.testing.assert_array_equal(
        matrix,
        [[2, 1, 1], [np.nan, 0, np.nan], [np.nan, np.nan, np.nan], [np.nan, 1, np.nan], [np.nan, 0, np.nan]],
    )


@pytest.mark.parametrize("parameter", ["learning_rate", "lambda_l1", "lambda_l2"])
@pytest.mark.parametrize("value", [float("inf"), -float("inf"), float("nan")])
def test_training_rejects_nonfinite_numeric_settings(parameter, value):
    from axonx_qlib_a158.train import LgbmTrainInputParams

    with pytest.raises(ValueError):
        LgbmTrainInputParams(**{parameter: value})


@pytest.mark.parametrize(
    "inputs",
    [
        {"train": {"parameter_preset": "qlib"}},
        {"train": {"label_column": "label_return_csz"}},
        {"backtest": {"as_of_date": "20261029"}},
    ],
)
def test_comparison_rejects_overrides_of_experiment_owned_inputs(inputs):
    from axonx_qlib_a158.comparison import ComparisonInputParams

    with pytest.raises(ValueError, match="Comparison owns"):
        ComparisonInputParams(upstream_task_ids=["etl#qlib_a158_etl#source"], **inputs)


def test_comparison_uses_stage_date_defaults_and_validates_before_training():
    from axonx_qlib_a158.comparison import ComparisonInputParams
    from axonx_qlib_a158.predict import LgbmPredictInputParams

    source = ["etl#qlib_a158_etl#source"]
    params = ComparisonInputParams(upstream_task_ids=source, train={"train_end": "20220101"})
    assert params.predict.pred_start == LgbmPredictInputParams().pred_start
    with pytest.raises(ValueError, match="pred_start"):
        ComparisonInputParams(upstream_task_ids=source, train={"train_end": "20250101"})
    with pytest.raises(ValueError, match="pred_start"):
        ComparisonInputParams(
            upstream_task_ids=source,
            train={"train_end": "20250101"},
            predict={"pred_start": "20250101", "pred_end": "20240101"},
        )
