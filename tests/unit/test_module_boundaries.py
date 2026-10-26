"""Keep module independence enforceable after moving shared capabilities."""

import ast
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SHARED = {"axonx.utils.logging", "axonx.utils.env", "axonx.utils.values"}
OWNERS = {"app", "cli", "utils", "daemon", "plugin", "task"}


def imports(path, *, include_type_checking=True):
    module = ".".join(path.relative_to(ROOT).with_suffix("").parts)
    package = module.rsplit(".", 1)[0]

    def walk(node):
        if (
            not include_type_checking
            and isinstance(node, ast.If)
            and ast.unparse(node.test)
            in {
                "TYPE_CHECKING",
                "typing.TYPE_CHECKING",
            }
        ):
            for child in node.orelse:
                yield from walk(child)
            return
        yield node
        for child in ast.iter_child_nodes(node):
            yield from walk(child)

    for node in walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom):
            name = node.module or ""
            if node.level:
                name = importlib.util.resolve_name("." * node.level + name, package)
            if name in {"axonx", "axonx.task"} or node.module is None:
                yield from (name + "." + alias.name for alias in node.names)
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
                allowed |= target.startswith("axonx.task.models.")
                allowed |= target == "axonx.task.query" or target.startswith("axonx.task.query.")
                allowed |= target in {
                    "axonx.task.storage.files",
                    "axonx.task.storage.logs",
                    "axonx.task.storage.workspace",
                }
            if owner == "plugin":
                allowed |= dependency == "task"
            if owner == "daemon":
                allowed |= target.startswith("axonx.app.")
                allowed |= target == "axonx.task.runtime.settings"
            if owner == "utils":
                allowed = False
            if not allowed:
                violations.append(f"{path.relative_to(ROOT)} -> {target}")
    assert not violations, "\n".join(violations)


def test_utils_are_flat_and_replace_common():
    assert not (ROOT / "axonx/common").exists()
    assert {path.name for path in (ROOT / "axonx/utils").glob("*.py")} == {
        "__init__.py",
        "logging.py",
        "env.py",
        "values.py",
    }
    assert not [path for path in (ROOT / "axonx/utils").iterdir() if path.is_dir() and path.name != "__pycache__"]


def test_task_data_contracts_do_not_load_business_operations():
    forbidden = (
        "axonx.app",
        "axonx.cli",
        "axonx.plugin",
        "axonx.task.core",
        "axonx.task.runtime",
        "axonx.task.storage",
        "axonx.task.query",
        "axonx.task.builtins",
    )
    for path in (ROOT / "axonx/task/models").glob("*.py"):
        assert not [target for target in imports(path) if target.startswith(forbidden)], path
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call):
                continue
            operation = node.func
            assert not (isinstance(operation, ast.Name) and operation.id == "open"), path
            assert not (
                isinstance(operation, ast.Attribute)
                and operation.attr in {"open", "read_text", "read_bytes", "write_text", "write_bytes", "stat", "lstat"}
            ), path


def test_task_package_has_only_capability_packages_and_its_initializer():
    root = ROOT / "axonx/task"
    assert {path.name for path in root.iterdir() if path.is_file()} == {"__init__.py"}
    assert {path.name for path in root.iterdir() if path.is_dir() and path.name != "__pycache__"} == {
        "models",
        "core",
        "runtime",
        "storage",
        "query",
        "builtins",
    }


def test_task_capabilities_follow_one_way_runtime_dependencies():
    dependencies = {
        "models": set(),
        "storage": {"models"},
        "core": {"models", "storage"},
        "runtime": {"models", "storage", "core"},
        "query": {"models", "storage"},
        "builtins": {"models", "storage", "core"},
    }
    violations = []
    for path in (ROOT / "axonx/task").rglob("*.py"):
        if path == ROOT / "axonx/task/__init__.py":
            # The public initializer explicitly exposes every capability package.
            continue
        owner = path.relative_to(ROOT / "axonx/task").parts[0]
        for target in imports(path, include_type_checking=False):
            if not target.startswith("axonx.task."):
                continue
            dependency = target.split(".")[2]
            if dependency != owner and dependency not in dependencies[owner]:
                violations.append(f"{path.relative_to(ROOT)} -> {target}")
    assert not violations, "\n".join(violations)


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
        (
            "axonx.task.runtime.settings",
            ("axonx.app", "axonx.cli", "axonx.plugin", "axonx.task.core", "axonx.task.storage"),
        ),
        ("axonx.task.core.composite", ("axonx.task.runtime", "axonx.plugin", "axonx.app")),
        ("axonx.task.storage.online", ("axonx.task.core", "axonx.task.runtime", "axonx.app")),
        ("axonx.task.query", ("axonx.task.core", "axonx.task.runtime", "axonx.plugin", "axonx.app")),
        (
            "axonx.app.components.sync.applier",
            (
                "axonx.app.components.sync.local",
                "axonx.app.components.client",
                "axonx.task.core",
                "axonx.task.runtime",
                "axonx.plugin",
            ),
        ),
        (
            "axonx.app.components.sync.index",
            ("axonx.app.components.sync.local", "axonx.app.components.client"),
        ),
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
    # Task exposes its packages eagerly. Check additional loads beyond that
    # public entry point; Plugin installation must still avoid Task entirely.
    initialize_task = "import axonx.task; " if module.startswith(("axonx.task.", "axonx.app.")) else ""
    code = (
        f"import sys; {initialize_task}baseline=set(sys.modules); import {module}; forbidden={forbidden!r}; "
        "loaded=[name for name in sys.modules if name not in baseline "
        "and any(name == item or name.startswith(item + '.') "
        "for item in forbidden)]; assert not loaded, loaded"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
