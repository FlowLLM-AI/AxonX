"""Built-in guide loading and Claude system prompt composition."""

from copy import deepcopy
from importlib.resources import files
from pathlib import Path

import pytest
from pydantic import ValidationError

from axonx.components.agent.claude.backend import ClaudeAgentComponent
from axonx.components.registry import ProviderRegistry
from axonx.config import ApplicationConfig, resolve_app_config
from axonx.core.context import ApplicationContext


@pytest.fixture
def context(tmp_path):
    return ApplicationContext(ProviderRegistry(), workspace_dir=str(tmp_path))


def test_language_defaults_and_validation():
    assert ApplicationConfig().language == "en"
    assert resolve_app_config(config="default", log_config=False)["language"] == "en"
    with pytest.raises(ValidationError):
        ApplicationConfig(language="fr")


@pytest.mark.parametrize("value", ["false", "true", 0, 1, None])
def test_guide_switch_requires_boolean(value):
    with pytest.raises(TypeError, match="load_dev_guide"):
        ClaudeAgentComponent(load_dev_guide=value)


@pytest.mark.asyncio
async def test_disabled_guide_does_not_read_resources(context, monkeypatch):
    def unexpected_read(*args):
        pytest.fail("Disabled guide must not read package resources")

    monkeypatch.setattr("axonx.components.agent.base.files", unexpected_read)
    prompt = {"type": "preset", "preset": "claude_code", "append": "Identity"}
    async with ClaudeAgentComponent(app_context=context, system_prompt=prompt) as agent:
        assert agent.dev_guide == ""
        options = agent._build_options(session_id="session", resume=False, depth=0)
        assert options.system_prompt == prompt


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["en", "zh"])
async def test_guide_language_and_startup_snapshot(context, language):
    context.app_config.language = language
    async with ClaudeAgentComponent(app_context=context, load_dev_guide=True) as agent:
        expected = Path(f"docs/{language}/dev_guide.md").read_text(encoding="utf-8")
        assert agent.dev_guide == expected
        context.app_config.language = "zh" if language == "en" else "en"
        for resume in (False, True):
            options = agent._build_options(session_id="session", resume=resume, depth=0)
            assert options.system_prompt == {"type": "preset", "preset": "claude_code", "append": expected}
        assert "load_dev_guide" not in agent.options


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "prompt",
    [
        "Identity",
        "",
        {"type": "preset", "preset": "claude_code", "append": "Identity", "exclude_dynamic_sections": True},
    ],
)
async def test_guide_preserves_prompt_without_mutating_options(context, prompt):
    original = deepcopy(prompt)
    async with ClaudeAgentComponent(app_context=context, load_dev_guide=True, system_prompt=prompt) as agent:
        for _ in range(2):
            options = agent._build_options(session_id="session", resume=False, depth=0)
            if isinstance(prompt, dict):
                assert options.system_prompt == {**original, "append": "Identity\n\n" + agent.dev_guide}
            else:
                assert options.system_prompt == (prompt + "\n\n" if prompt else "") + agent.dev_guide
        assert agent.options["system_prompt"] == original
        assert prompt == original


@pytest.mark.asyncio
@pytest.mark.parametrize("absolute", [False, True])
async def test_guide_appends_to_file_prompt_from_agent_cwd(context, absolute):
    directory = Path(context.app_config.workspace_dir) / "project"
    directory.mkdir()
    path = directory / "prompt.txt"
    path.write_text("Custom instructions", encoding="utf-8")
    prompt = {"type": "file", "path": str(path) if absolute else "prompt.txt"}
    async with ClaudeAgentComponent(
        app_context=context, cwd="project", load_dev_guide=True, system_prompt=prompt
    ) as agent:
        options = agent._build_options(session_id="session", resume=True, depth=0)
        assert options.system_prompt == "Custom instructions\n\n" + agent.dev_guide
        assert agent.options["system_prompt"] == prompt


@pytest.mark.asyncio
async def test_enabled_guide_missing_resource_fails_startup(context, monkeypatch):
    def missing_resource(*args):
        raise FileNotFoundError("Missing guide")

    monkeypatch.setattr("axonx.components.agent.base.files", missing_resource)
    agent = ClaudeAgentComponent(app_context=context, load_dev_guide=True)
    with pytest.raises(FileNotFoundError, match="Missing guide"):
        await agent.start()
    assert not agent.is_started
    assert agent._store is None


@pytest.mark.asyncio
async def test_standalone_agent_uses_english(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    async with ClaudeAgentComponent(load_dev_guide=True) as agent:
        assert agent.dev_guide == files("axonx.components.agent").joinpath("guides/en.md").read_text(encoding="utf-8")
