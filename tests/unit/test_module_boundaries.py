"""Keep module independence enforceable after moving shared capabilities."""

import ast
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SHARED = {"axonx.utils.async_work", "axonx.utils.logging", "axonx.utils.env", "axonx.utils.values"}
OWNERS = {"app", "client", "cli", "utils", "daemon", "plugin", "task"}
CLIENT_RUNTIME_FORBIDDEN = (
    "axonx.app",
    "axonx.task.core",
    "axonx.task.runtime",
    "axonx.task.storage",
    "axonx.task.builtins",
    "axonx.cli",
    "axonx.daemon",
    "axonx.plugin",
    "fastapi",
    "fastmcp",
    "claude_agent_sdk",
    "polars",
    "pyarrow",
)


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


def test_all_task_models_depend_only_on_data_contracts():
    violations = [
        f"{path.name} -> {target}"
        for path in (ROOT / "axonx/task/models").glob("*.py")
        for target in imports(path)
        if target.startswith("axonx.") and not target.startswith("axonx.task.models.")
    ]
    assert not violations, "\n".join(violations)
    code = """
import importlib
import pkgutil
import sys
import axonx.task.models

for module in pkgutil.iter_modules(axonx.task.models.__path__):
    importlib.import_module(f"axonx.task.models.{module.name}")
forbidden = (
    "axonx.app", "axonx.cli", "axonx.plugin", "axonx.daemon",
    "axonx.task.core", "axonx.task.runtime", "axonx.task.storage", "axonx.task.builtins",
    "polars", "pyarrow",
)
loaded = [name for name in sys.modules if name.startswith(forbidden)]
assert not loaded, loaded
"""
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_cross_module_imports_follow_the_public_contracts():
    violations = []
    for path in (ROOT / "axonx").rglob("*.py"):
        owner = path.relative_to(ROOT / "axonx").parts[0]
        if owner not in OWNERS:
            continue
        runtime_imports = set(imports(path, include_type_checking=False))
        for target in imports(path):
            if not target.startswith("axonx."):
                continue
            dependency = target.split(".")[1]
            if dependency == owner or target == "axonx._version":
                continue
            allowed = owner == "cli" or target in SHARED
            if owner == "app":
                allowed |= dependency == "client"
                allowed |= target.startswith("axonx.task.models.")
                allowed |= target == "axonx.task.runtime.catalog" and target not in runtime_imports
                allowed |= target in {
                    "axonx.task.storage.files",
                    "axonx.task.storage.logs",
                    "axonx.task.storage.workspace",
                }
            if owner == "client":
                allowed = target == "axonx.task.models.events" or target in SHARED
            if owner == "daemon":
                allowed |= target.startswith("axonx.app.")
                allowed |= target == "axonx.task.runtime.settings"
                allowed |= target == "axonx.task.runtime.catalog"
                allowed |= target == "axonx.plugin.discovery"
                allowed |= target == "axonx.client.config"
            if owner == "utils":
                allowed = False
            if not allowed:
                violations.append(f"{path.relative_to(ROOT)} -> {target}")
    assert not violations, "\n".join(violations)


def test_utils_are_flat_and_replace_common():
    assert not (ROOT / "axonx/common").exists()
    assert {path.name for path in (ROOT / "axonx/utils").glob("*.py")} == {
        "__init__.py",
        "async_work.py",
        "logging.py",
        "env.py",
        "values.py",
    }
    assert not [path for path in (ROOT / "axonx/utils").iterdir() if path.is_dir() and path.name != "__pycache__"]


def test_app_has_only_its_five_capabilities_and_complete_module_namespaces():
    root = ROOT / "axonx/app"
    assert {path.name for path in root.iterdir() if path.is_file()} == {"__init__.py"}
    assert {path.name for path in root.iterdir() if path.is_dir() and path.name != "__pycache__"} == {
        "components",
        "config",
        "core",
        "steps",
        "workspace",
    }
    for path in root.rglob("__init__.py"):
        tree = ast.parse(path.read_text())
        doc = ast.get_docstring(tree)
        assert doc, path
        if path == root / "__init__.py":
            assert len(tree.body) == 1, f"Package initializer loads or re-exports capabilities: {path}"
            continue
        expected = {
            *(child.stem for child in path.parent.glob("*.py") if child.name != "__init__.py"),
            *(child.name for child in path.parent.iterdir() if child.is_dir() and (child / "__init__.py").is_file()),
        }
        exports = next(
            ast.literal_eval(node.value)
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(name, ast.Name) and name.id == "__all__" for name in node.targets)
        )
        assert sorted(exports) == sorted(expected), path
        assert all(f"\n{name}:" in doc for name in expected), path


def test_app_capabilities_follow_their_runtime_ownership():
    dependencies = {
        "components": {"config", "workspace"},
        "config": set(),
        "core": {"components", "config", "steps", "workspace"},
        "steps": {"components", "config", "workspace"},
        "workspace": set(),
    }
    violations = []
    for path in (ROOT / "axonx/app").rglob("*.py"):
        if path.name == "__init__.py":
            continue
        owner = path.relative_to(ROOT / "axonx/app").parts[0]
        for target in imports(path, include_type_checking=False):
            if not target.startswith("axonx.app."):
                continue
            dependency = target.split(".")[2]
            if dependency == owner or dependency in dependencies[owner]:
                continue
            # Pipeline execution consumes the Step interface; composition selects concrete Steps.
            if path.name == "pipeline.py" and target == "axonx.app.steps.base":
                continue
            violations.append(f"{path.relative_to(ROOT)} -> {target}")
    assert not violations, "\n".join(violations)


def test_app_models_keep_data_only_dependencies_and_config_stays_independent():
    paths = sorted((ROOT / "axonx/app").rglob("models.py"))
    allowed = {"axonx.client.config", "axonx.client.events"}
    for path in paths:
        assert not [target for target in imports(path) if target.startswith("axonx.") and target not in allowed], path
    code = """
import sys
import axonx.app.config.models
forbidden = (
    "axonx.app.core", "axonx.app.steps", "axonx.app.components.base",
    "axonx.app.components.registry", "axonx.app.components.machine.build_info",
    "axonx.app.components.machine.base", "axonx.app.components.machine.local", "axonx.app.components.machine.gpu",
    "axonx.app.components.machine.python",
    "axonx.app.components.agent.claude", "axonx.app.components.service.http.service",
    "axonx.app.components.sync.local", "axonx.app.workspace.core",
    "axonx.client.http", "axonx.client.mcp", "axonx.task.runtime", "axonx.task.storage",
    "fastapi", "fastmcp", "httpx", "claude_agent_sdk", "psutil", "polars", "pyarrow",
)
loaded = [name for name in sys.modules if name.startswith(forbidden)]
assert not loaded, loaded
"""
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_task_data_contracts_do_not_load_business_operations():
    forbidden = (
        "axonx.app",
        "axonx.cli",
        "axonx.plugin",
        "axonx.task.core",
        "axonx.task.runtime",
        "axonx.task.storage",
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
        "builtins",
    }


def test_task_capabilities_follow_one_way_runtime_dependencies():
    dependencies = {
        "models": set(),
        "storage": {"models"},
        "core": {"models", "storage"},
        "runtime": {"models", "storage", "core", "builtins"},
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
    for filename in ("supervisor.py", "client.py", "update.py"):
        path = ROOT / "axonx/daemon" / filename
        assert all(
            target.split(".")[0] in sys.stdlib_module_names
            or target.startswith("axonx.daemon")
            or (filename == "supervisor.py" and target == "update")
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
            "axonx.task",
            (
                "axonx.task.models",
                "axonx.task.core",
                "axonx.task.runtime",
                "axonx.task.storage",
                "axonx.task.builtins",
            ),
        ),
        (
            "axonx.client",
            CLIENT_RUNTIME_FORBIDDEN
            + (
                "axonx.client.base",
                "axonx.client.http",
                "axonx.client.mcp",
                "axonx.client.models",
                "axonx.client.events",
                "axonx.task",
            ),
        ),
        ("axonx.client.base", CLIENT_RUNTIME_FORBIDDEN),
        ("axonx.client.http", CLIENT_RUNTIME_FORBIDDEN),
        ("axonx.client.mcp", CLIENT_RUNTIME_FORBIDDEN),
        (
            "axonx.client.models",
            CLIENT_RUNTIME_FORBIDDEN
            + ("axonx.client.base", "axonx.client.http", "axonx.client.mcp", "axonx.task", "httpx"),
        ),
        (
            "axonx.client.config",
            CLIENT_RUNTIME_FORBIDDEN
            + ("axonx.client.base", "axonx.client.http", "axonx.client.mcp", "axonx.task", "httpx"),
        ),
        (
            "axonx.client.events",
            CLIENT_RUNTIME_FORBIDDEN + ("axonx.client.base", "axonx.client.http", "axonx.client.mcp", "httpx"),
        ),
        (
            "axonx.utils.async_work",
            ("axonx.app", "axonx.task", "axonx.client", "axonx.cli", "axonx.daemon", "axonx.plugin"),
        ),
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
        ("axonx.task.runtime.catalog", ("axonx.app", "axonx.cli", "axonx.plugin", "axonx.daemon")),
        ("axonx.plugin.discovery", ("axonx.app", "axonx.cli", "axonx.task", "axonx.daemon")),
        (
            "axonx.task.runtime.settings",
            ("axonx.app", "axonx.cli", "axonx.plugin", "axonx.task.core", "axonx.task.storage"),
        ),
        ("axonx.task.core.base", ("axonx.task.runtime", "axonx.plugin", "axonx.app")),
        ("axonx.task.storage.online", ("axonx.task.core", "axonx.task.runtime", "axonx.app")),
        ("axonx.app.components.task_index", ("axonx.task.core", "axonx.task.runtime", "axonx.plugin")),
        (
            "axonx.app.components.sync.applier",
            (
                "axonx.task.core",
                "axonx.task.runtime",
                "axonx.plugin",
            ),
        ),
        ("axonx.plugin.installer", ("axonx.app", "axonx.cli", "axonx.daemon")),
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
        f"import sys; import {module}; forbidden={forbidden!r}; "
        "loaded=[name for name in sys.modules "
        "if any(name == item or name.startswith(item + '.') "
        "for item in forbidden)]; assert not loaded, loaded"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("module", ["applier", "archive", "artifacts"])
def test_sync_archive_helpers_do_not_depend_on_transfer_components(module):
    # The package exposes all namespaces; implementation dependencies stay separate.
    forbidden = ("axonx.app.components.sync.local", "axonx.client")
    path = ROOT / "axonx/app/components/sync" / f"{module}.py"
    assert not [target for target in imports(path) if target.startswith(forbidden)], path


@pytest.mark.parametrize(
    "first",
    [
        "axonx.client",
        "axonx.client.http",
        "axonx.app",
        "axonx.app.components",
        "axonx.app.config",
        "axonx.app.core",
        "axonx.app.steps",
        "axonx.app.workspace",
        "axonx.cli",
    ],
)
def test_service_clients_import_independently_of_application_import_order(first):
    code = f"""
import {first}
import importlib.util
from axonx.app import components
from axonx.app.components.base import BaseComponent
from axonx.app.core.application import Application
from axonx.client.base import BaseClient
from axonx.client.http import HttpClient
from axonx.client.mcp import McpClient
import axonx.client
from axonx.app.workspace import models as workspace_models

assert not issubclass(BaseClient, BaseComponent)
assert issubclass(HttpClient, BaseClient)
assert issubclass(McpClient, BaseClient)
assert not hasattr(components, "client")
assert not hasattr(axonx.client, "HttpClient")
assert importlib.util.find_spec("axonx.app.components.job.events") is None
assert not hasattr(workspace_models, "StagedFile")
assert importlib.util.find_spec("axonx.app.components.client") is None
assert importlib.util.find_spec("axonx.app.async_work") is None
assert importlib.util.find_spec("axonx.app.connection") is None
assert importlib.util.find_spec("axonx.app.protocol") is None
assert importlib.util.find_spec("axonx.app.components.job.models") is None
assert importlib.util.find_spec("axonx.app.components.agent.events") is None
"""
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
