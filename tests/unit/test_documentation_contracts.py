"""Check published examples against the current CLI, Job and Task contracts."""

import importlib
import json
import re
import shlex
from pathlib import Path

import jsonschema
import pytest
import yaml

from axonx.cli.parser import parse_command, parse_plugin_arguments
from axonx.task.builtins.demo import DemoTask
from axonx.task.runtime.executor import TaskExecutor

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
FENCES = re.compile(r"^```(\w+)\n(.*?)^```", re.MULTILINE | re.DOTALL)


def job_schemas():
    return yaml.safe_load((ROOT / "axonx/app/config/default.yaml").read_text())["jobs"]


def test_distributable_skill_body_matches_english_guide():
    skill = (ROOT / "skills/axonx/SKILL.md").read_text()
    metadata, separator, body = skill.partition("\n---\n")
    assert separator
    assert yaml.safe_load(metadata.removeprefix("---\n"))["name"] == "axonx"
    assert body.removeprefix("\n") == (DOCS / "en/dev_guide.md").read_text()


def test_translated_development_guides_have_identical_examples():
    english = (DOCS / "en/dev_guide.md").read_text()
    chinese = (DOCS / "zh/dev_guide.md").read_text()
    assert FENCES.findall(english) == FENCES.findall(chinese)


@pytest.mark.parametrize(
    "relative_path",
    ["skills/axonx/SKILL.md", "docs/en/dev_guide.md", "docs/zh/dev_guide.md"],
)
def test_development_guides_are_standalone_files(relative_path):
    path = ROOT / relative_path
    assert not path.is_symlink()
    prose = FENCES.sub("", path.read_text())
    assert not re.search(r"!?\[[^\]\n]+\]\s*\(|^\s*\[[^\]\n]+\]:", prose, re.MULTILINE)
    assert not re.search(r"<(?:a|img)\b", prose, re.IGNORECASE)


@pytest.mark.parametrize("language", ["en", "zh"])
def test_api_examples_cover_and_validate_configured_jobs(language):
    jobs = job_schemas()
    documented = set()
    for page in sorted((DOCS / language / "api").glob("*.md")):
        for section in re.split(r"^## ", page.read_text(), flags=re.MULTILINE)[1:]:
            name = section.splitlines()[0]
            if name not in jobs:
                continue
            for fence_language, body in FENCES.findall(section):
                if fence_language == "json":
                    payload = json.loads(body)
                    jsonschema.validate(payload["arguments"], jobs[name].get("parameters", {}))
                    documented.add(name)
    assert documented == jobs.keys()


def test_documented_cli_commands_use_current_grammar_and_job_schemas():
    jobs = job_schemas()
    count = 0
    for page in sorted(DOCS.rglob("*.md")):
        for language, body in FENCES.findall(page.read_text()):
            if language not in {"bash", "sh"}:
                continue
            for line in body.replace("\\\n", " ").splitlines():
                if not line.strip().startswith("axonx "):
                    continue
                argv = shlex.split(line.strip(), comments=True)[1:]
                if argv in (["--help"], ["-h"]):
                    continue
                command, _ = parse_command(argv)
                count += 1
                if command.action == "plugin":
                    parse_plugin_arguments(command.raw_arguments)
                elif command.action not in {"app", "exec", "kill"}:
                    assert command.action in jobs, (page, line)
                    arguments = dict(command.arguments)
                    # These documented placeholders must be replaced by a real returned ID.
                    if "session_id" in arguments and "<" in str(arguments["session_id"]):
                        arguments["session_id"] = "01234567-89ab-4cde-8f01-23456789abcd"
                    if arguments.get("update_id") == "ACTUAL_UPDATE_ID":
                        arguments["update_id"] = "0" * 32
                    jsonschema.validate(arguments, jobs[command.action].get("parameters", {}))
    assert count > 0


def test_documented_python_imports_resolve():
    for page in sorted(DOCS.rglob("*.md")):
        for language, body in FENCES.findall(page.read_text()):
            if language != "python":
                continue
            for module_name, imported in re.findall(r"^from (axonx[\w.]*) import (.+)$", body, re.MULTILINE):
                module = importlib.import_module(module_name)
                for entry in imported.split(","):
                    name = entry.strip().split(" as ")[0]
                    assert hasattr(module, name), (page, module_name, name)


@pytest.mark.parametrize("language", ["en", "zh"])
def test_task_authoring_examples_execute(tmp_path, language):
    examples = [
        ("dev_guide", "AddTask", {"x": 1, "y": 2}, 3),
        ("guides/composite-tasks", "DemoChainTask", {}, 7),
    ]
    for route, class_name, inputs, expected in examples:
        page = DOCS / language / f"{route}.md"
        source = next(body for kind, body in FENCES.findall(page.read_text()) if kind == "python")
        namespace = {}
        # Execute the published plugin source to check its actual behavior.
        exec(compile(source, str(page), "exec"), namespace)  # pylint: disable=exec-used
        task = namespace[class_name](
            {"task_name": class_name, **inputs},
            workspace_path=tmp_path,
            reg_name="docs_example",
        )
        result = TaskExecutor(resolve_task=lambda name: {"demo": DemoTask}[name]).execute(task)
        assert result.exit_code == 0
        assert result.output_params["total"] == expected
