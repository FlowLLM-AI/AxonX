"""Keep module independence enforceable after moving shared capabilities."""

import ast
import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
SHARED = {"axonx.common.logging", "axonx.common.env"}
OWNERS = {"app", "cli", "common", "daemon", "plugin", "task"}


def imports(path):
    module = ".".join(path.relative_to(ROOT).with_suffix("").parts)
    package = module.rsplit(".", 1)[0]
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom):
            name = node.module or ""
            if node.level:
                name = importlib.util.resolve_name("." * node.level + name, package)
            if name == "axonx":
                yield from ("axonx." + alias.name for alias in node.names)
            else:
                yield name
        elif isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)


def test_cross_module_imports_follow_the_public_contracts():
    violations = []
    for path in (ROOT / "axonx").rglob("*.py"):
        owner = path.relative_to(ROOT / "axonx").parts[0]
        if owner not in OWNERS:
            continue
        for target in imports(path):
            if not target.startswith("axonx."):
                continue
            dependency = target.split(".")[1]
            if dependency == owner or target == "axonx._version":
                continue
            allowed = owner == "cli" or target in SHARED
            if owner == "app":
                allowed |= target == "axonx.task.task_enums" or target.startswith("axonx.task.models.")
                allowed |= target == "axonx.task.query" or target.startswith(
                    (
                        "axonx.task.query.",
                        "axonx.task.sync.",
                    )
                )
                allowed |= target in {"axonx.task.storage.logs", "axonx.task.storage.workspace"}
            if owner == "plugin":
                allowed |= dependency == "task"
            if owner == "daemon":
                allowed |= target.startswith("axonx.app.")
                allowed |= target == "axonx.task.runtime.settings"
            if owner == "common":
                allowed = False
            if not allowed:
                violations.append(f"{path.relative_to(ROOT)} -> {target}")
    assert not violations, "\n".join(violations)


def test_common_has_only_logging_and_env():
    assert {path.name for path in (ROOT / "axonx/common").glob("*.py")} == {"__init__.py", "logging.py", "env.py"}
    assert not [path for path in (ROOT / "axonx/common").iterdir() if path.is_dir() and path.name != "__pycache__"]


def test_task_data_contracts_do_not_load_business_operations():
    forbidden = (
        "axonx.app",
        "axonx.cli",
        "axonx.plugin",
        "axonx.task.core",
        "axonx.task.runtime",
        "axonx.task.storage",
        "axonx.task.query",
        "axonx.task.sync",
    )
    for path in (ROOT / "axonx/task/models").glob("*.py"):
        assert not [target for target in imports(path) if target.startswith(forbidden)], path


def test_daemon_uses_only_standard_library_and_injected_commands():
    for filename in ("worker.py", "client.py", "update.py", "update_worker.py"):
        path = ROOT / "axonx/daemon" / filename
        assert all(
            target.split(".")[0] in sys.stdlib_module_names or target.startswith("axonx.daemon")
            for target in imports(path)
        ), path
        assert "axonx.cli" not in path.read_text(), path


def test_cli_does_not_implement_resident_components_or_steps():
    resident_bases = {"BaseComponent", "BaseTaskIndex", "BaseSyncComponent", "BaseStep", "BaseJob"}
    for path in (ROOT / "axonx/cli").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ClassDef):
                assert not resident_bases.intersection(ast.unparse(base) for base in node.bases), path


@pytest.mark.parametrize(
    ("module", "forbidden"),
    [
        (
            "axonx.app.core.application",
            (
                "axonx.cli",
                "axonx.plugin",
                "axonx.daemon",
                "axonx.task.core",
                "axonx.task.runtime",
            ),
        ),
        ("axonx.task.runtime.executor", ("axonx.app", "axonx.cli", "axonx.plugin", "axonx.daemon")),
        ("axonx.plugin.installer", ("axonx.app", "axonx.cli", "axonx.task", "axonx.daemon")),
        (
            "axonx.task.models.params",
            (
                "axonx.app",
                "axonx.cli",
                "axonx.plugin",
                "axonx.task.core",
                "axonx.task.runtime",
                "axonx.task.storage",
            ),
        ),
    ],
)
def test_importing_one_capability_does_not_load_other_runtimes(module, forbidden):
    code = (
        f"import {module}; import sys; forbidden={forbidden!r}; "
        "loaded=[name for name in sys.modules if any(name == item or name.startswith(item + '.') "
        "for item in forbidden)]; assert not loaded, loaded"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
