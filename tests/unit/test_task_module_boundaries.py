"""Task module moves preserve public objects and keep schemas independent."""

import ast
import importlib
import importlib.util
from pathlib import Path
import sys

import pytest

from axonx.task import schemas


@pytest.mark.parametrize(
    ("legacy", "canonical", "names"),
    [
        ("artifact", "schemas.artifact", ["ArtifactRecord"]),
        ("status", "schemas.lifecycle", ["TaskStatus"]),
        ("source", "schemas.lifecycle", ["TaskSource"]),
        ("clock", "core.clock", ["WindowClock", "ReplayClock"]),
        ("composite", "core.composite", ["BaseCompositeTask", "ChildTaskError", "ChildTaskResult"]),
        (
            "protocol",
            "schemas.protocol",
            [
                "PROTOCOL_VERSION",
                "STOCK_SIGNALS_FORMAT",
                "Protocol",
                "fingerprint",
                "task_protocol",
                "validate_protocol",
            ],
        ),
        ("protocol", "schemas.model", ["ModelCollection", "ModelMember"]),
        ("protocol", "schemas.prediction", ["PredictionProtocol"]),
        ("protocol", "storage.artifacts", ["prediction_protocol"]),
        ("storage.workspace", "schemas.lifecycle", ["TaskMetadata", "ChildTaskRecord"]),
        ("storage.replica", "schemas.replica", ["DisplayReplica", "LiveSnapshot", "ReplicaFile", "ReplicaLog"]),
        ("storage.composition", "schemas.lifecycle", ["current_children"]),
        ("contracts.online", "schemas.online", ["OnlineCommit", "OnlineHistory"]),
        ("contracts.online", "schemas.reports", ["StockOnlineReport", "StockReportSettings", "STOCK_REPORT_ARTIFACTS"]),
        (
            "contracts.backtest",
            "schemas.reports",
            ["BacktestBenchmark", "BacktestDimensions", "BacktestUniverse", "BacktestUniverseReport"],
        ),
        ("contracts.windows", "core.clock", ["DeadlineBudget", "WindowClock"]),
        ("contracts", "schemas.online", ["OnlineCommit", "OnlineHistory"]),
        ("", "core.composite", ["BaseCompositeTask", "ChildTaskError", "ChildTaskResult"]),
        ("", "schemas.lifecycle", ["TaskMetadata"]),
    ],
)
def test_legacy_imports_share_canonical_objects(legacy, canonical, names):
    old = importlib.import_module("axonx.task" + ("." + legacy if legacy else ""))
    new = importlib.import_module("axonx.task." + canonical)
    for name in names:
        assert getattr(old, name) is getattr(new, name), name


def test_schemas_do_not_import_execution_storage_or_task_authoring():
    directory = Path(schemas.__file__).parent
    for path in directory.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                module = "." * node.level + (node.module or "")
                modules = [importlib.util.resolve_name(module, schemas.__name__)] if node.level else [module]
            elif isinstance(node, ast.Import):
                modules = [item.name for item in node.names]
            else:
                continue
            for module in modules:
                assert (
                    module.split(".")[0] in sys.stdlib_module_names
                    or module.split(".")[0] in {"__future__", "pydantic"}
                    or module in {"axonx.enums", "axonx.progress"}
                    or module.startswith("axonx.task.schemas.")
                ), (path.name, module)
