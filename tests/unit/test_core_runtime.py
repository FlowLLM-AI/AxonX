"""Contracts for explicit providers, dependency injection, and lifecycle."""

import asyncio
from threading import Event
from unittest.mock import AsyncMock

import pytest

from axonx.components.agent import ClaudeAgentComponent
from axonx.components.base import BaseComponent
from axonx.components.registry import ProviderRegistry, provider
from axonx.constants import CLI_RAW_ARGUMENTS
from axonx.core import Application
from axonx.core.graph import ComponentGraph
from axonx.enums import ComponentEnum
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
    registry = ProviderRegistry.from_builtins()

    assert registry.require(ComponentEnum.AGENT, "claude", BaseComponent) is ClaudeAgentComponent


def test_application_context_indexes_are_read_only_after_composition(tmp_path):
    app = Application(**_config(tmp_path, jobs={"empty": {}}))

    with pytest.raises(TypeError):
        app.context.jobs["other"] = app.context.jobs["empty"]
    with pytest.raises(RuntimeError, match="already finalized"):
        app.context._set_jobs({})


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
    assert not hasattr(manager, "repository")

    assert graph.resolve() == (repository, manager)
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


async def test_application_owns_periodic_log_cleanup_across_restarts(tmp_path, monkeypatch):
    loop = asyncio.get_running_loop()
    cleaned = asyncio.Event()
    directories = []

    def cleanup(directory):
        directories.append(directory)
        if len(directories) == 1:
            raise OSError("temporary cleanup failure")
        loop.call_soon_threadsafe(cleaned.set)

    monkeypatch.setattr("axonx.core.application.cleanup_log_files", cleanup)
    monkeypatch.setattr("axonx.core.application.LOG_CLEANUP_INTERVAL", 0.01)
    app = Application(**_config(tmp_path / "workspace", log_dir=str(tmp_path / "logs"), log_to_file=True))
    try:
        for _ in range(2):
            cleaned.clear()
            async with app:
                await asyncio.wait_for(cleaned.wait(), timeout=2)
                task = app._log_cleanup_task
                await app.start()
                assert app._log_cleanup_task is task
            assert task.cancelled()
            assert app._log_cleanup_task is None
        assert directories and all(directory == tmp_path / "logs" for directory in directories)
    finally:
        await app.close()
        from axonx.utils.logging import LoggingConfig, configure_logging

        configure_logging(LoggingConfig(log_to_console=False, log_to_file=False))


async def test_application_waits_for_inflight_log_cleanup_on_close(tmp_path, monkeypatch):
    entered = Event()
    release = Event()

    def cleanup(_directory):
        entered.set()
        release.wait(timeout=5)

    monkeypatch.setattr("axonx.core.application.cleanup_log_files", cleanup)
    # Initial cleanup must start immediately, independently of the hourly interval.
    monkeypatch.setattr("axonx.core.application.LOG_CLEANUP_INTERVAL", 3600)
    app = Application(**_config(tmp_path / "workspace", log_dir=str(tmp_path / "logs"), log_to_file=True))
    closing = None
    try:
        await app.start()
        assert await asyncio.to_thread(entered.wait, 2)
        closing = asyncio.create_task(app.close())
        await asyncio.sleep(0)
        assert not closing.done()
        release.set()
        await asyncio.wait_for(closing, timeout=2)
        assert app._log_cleanup_task is None
    finally:
        release.set()
        if closing is not None:
            await closing
        await app.close()
        from axonx.utils.logging import LoggingConfig, configure_logging

        configure_logging(LoggingConfig(log_to_console=False, log_to_file=False))


async def test_failed_log_cleanup_does_not_skip_component_shutdown(tmp_path):
    app = Application(**_config(tmp_path))
    await app.start()
    component = AsyncMock()
    app._started.append(component)

    async def failed_cleanup():
        raise RuntimeError("cleanup stopped")

    app._log_cleanup_task = asyncio.create_task(failed_cleanup())
    await asyncio.sleep(0)
    with pytest.raises(ExceptionGroup, match="Application cleanup failed") as error:
        await app.close()
    assert str(error.value.exceptions[0]) == "cleanup stopped"
    component.close.assert_awaited_once()
    assert app._log_cleanup_task is None
    assert not app.is_started
    await app.close()
