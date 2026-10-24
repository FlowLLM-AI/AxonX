"""Guard independent subsystem imports and schema-only data contracts."""

import ast
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from axonx.task import schemas

ROOT = Path(__file__).resolve().parents[2]
ALLOWED = {
    "common": set(),
    "config": {"common"},
    "plugin": {"config", "common"},
    "task": {"plugin", "config", "common"},
    "daemon": set(),
    "cron": {"config", "common"},
    "app": {"config", "plugin", "task", "common", "daemon"},
    "cli": {"app", "config", "plugin", "task", "common", "daemon", "cron"},
}


def imports(path, package):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            name = "." * node.level + (node.module or "")
            yield importlib.util.resolve_name(name, package) if node.level else name
        elif isinstance(node, ast.Import):
            yield from (item.name for item in node.names)


def test_eight_modules_have_no_reverse_dependencies():
    for path in (ROOT / "axonx").rglob("*.py"):
        relative = path.relative_to(ROOT)
        if len(relative.parts) < 3 or "__pycache__" in relative.parts:
            continue
        owner = relative.parts[1]
        assert owner in ALLOWED, relative
        module = ".".join(relative.with_suffix("").parts)
        package = module.rpartition(".")[0]
        for target in imports(path, package):
            assert target != "axonx", (relative, "Use a canonical subsystem import, not the root facade")
            parts = target.split(".")
            if len(parts) > 1 and parts[0] == "axonx" and parts[1] in ALLOWED:
                assert parts[1] == owner or parts[1] in ALLOWED[owner], (relative, target)


@pytest.mark.parametrize("module", ["common.arguments", "config", "plugin", "task", "cron", "daemon", "cli"])
def test_fresh_import_does_not_load_the_application(module):
    code = f"import importlib, sys; importlib.import_module('axonx.{module}'); " + (
        "assert not any(name == 'axonx.app' or name.startswith('axonx.app.') for name in sys.modules); "
        "assert 'fastapi' not in sys.modules; assert 'claude_agent_sdk' not in sys.modules"
    )
    if module != "task":
        code += "; assert not any(name == 'axonx.task' or name.startswith('axonx.task.') for name in sys.modules)"
    subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True, timeout=20)


def test_schemas_do_not_import_execution_storage_or_task_authoring():
    directory = Path(schemas.__file__).parent
    for path in directory.glob("*.py"):
        for target in imports(path, schemas.__name__):
            assert (
                target.split(".")[0] in sys.stdlib_module_names
                or target.split(".")[0] in {"__future__", "pydantic"}
                or target.startswith("axonx.common.")
                or target == "axonx.task.enums"
                or target.startswith("axonx.task.schemas.")
            ), (path.name, target)
