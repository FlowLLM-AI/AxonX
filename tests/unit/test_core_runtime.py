"""Contracts for explicit providers, dependency injection, and lifecycle."""

import pytest

from axonx.components.agent import ClaudeAgentComponent
from axonx.components.base import BaseComponent
from axonx.components.registry import ProviderRegistry, provider
from axonx.constants import CLI_RAW_ARGUMENTS
from axonx.core import Application
from axonx.core.graph import ComponentGraph
from axonx.enums import ComponentEnum
from axonx.providers import create_builtin_registry
from axonx.steps.base import BaseStep


def _config(tmp_path, **values):
    return {
        "workspace_dir": str(tmp_path),
        "enable_logo": False,
        "log_to_console": False,
        "log_to_file": False,
        **values,
    }


def test_registry_is_explicit_and_rejects_ambiguous_owners():
    @provider("same")
    class First(BaseComponent):
        component_type = ComponentEnum.SYNC

    @provider("same")
    class Second(BaseComponent):
        component_type = ComponentEnum.SYNC

    registry = ProviderRegistry()
    registry.add(First, owner="first")

    with pytest.raises(ValueError, match="first.*second"):
        registry.add(Second, owner="second")


def test_builtin_provider_is_registered_by_decorator():
    registry = create_builtin_registry()

    assert (
        registry.require(ComponentEnum.AGENT, "claude", BaseComponent)
        is ClaudeAgentComponent
    )


def test_graph_injects_dependencies_after_validating_order():
    class Repository(BaseComponent):
        component_type = ComponentEnum.TASK_REPOSITORY

    class Manager(BaseComponent):
        component_type = ComponentEnum.TASK_MANAGER
        repository: Repository

        def __init__(self):
            super().__init__()
            self.depend("repository", "main", Repository)

    repository = Repository()
    manager = Manager()
    graph = ComponentGraph(
        {
            "task_manager": {"main": manager},
            "task_repository": {"main": repository},
        }
    )

    assert graph.startup_order() == (repository, manager)
    assert manager.repository is repository


@pytest.mark.asyncio
async def test_component_preserves_startup_and_rollback_failures():
    class Broken(BaseComponent):
        async def _start(self):
            raise ValueError("start")

        async def _close(self):
            raise RuntimeError("rollback")

    with pytest.raises(BaseExceptionGroup) as raised:
        await Broken().start()

    assert [str(error) for error in raised.value.exceptions] == ["start", "rollback"]


def test_application_local_provider_does_not_leak(tmp_path):
    @provider("private_step")
    class PrivateStep(BaseStep):
        async def execute(self):
            pass

    Application(
        providers=[PrivateStep],
        **_config(
            tmp_path / "one",
            jobs={"private": {"steps": [{"backend": "private_step"}]}},
        ),
    )

    with pytest.raises(ValueError, match="Unknown step backend: private_step"):
        Application(
            **_config(
                tmp_path / "two",
                jobs={"private": {"steps": [{"backend": "private_step"}]}},
            )
        )


@pytest.mark.asyncio
async def test_public_arguments_cannot_enter_the_system_channel(tmp_path):
    app = Application(**_config(tmp_path, jobs={"empty": {}}))

    async with app:
        with pytest.raises(ValueError, match="Reserved Job argument"):
            await app.run_job("empty", {CLI_RAW_ARGUMENTS: ["--task", "demo"]})
