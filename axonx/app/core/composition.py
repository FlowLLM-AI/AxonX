"""Compose one complete, isolated application runtime."""

# Internal wiring intentionally uses private runtime hooks.
# pylint: disable=protected-access

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from ...utils.logging import LoggingConfig, configure_logging, get_logger
from ..components.agent.claude.backend import ClaudeAgentComponent
from ..components.base import BaseComponent
from ..components.cron.scheduler import CronComponent, ScheduledLaunch
from ..components.job.base import BaseJob
from ..components.job.pipeline import PipelineJob
from ..components.proxy.http import HttpProxyComponent
from ..components.registry import ProviderRegistry
from ..components.service.base import BaseService
from ..components.service.http.service import HttpService
from ..components.sync.local import LocalSyncComponent
from ..components.task_index.local import LocalTaskIndex
from ..components.updater.base import UpdateBackend
from ..components.updater.manager import UpdateManager
from ..config.models import ApplicationConfig, ComponentConfig
from ..steps.agent.run import AgentStreamStep
from ..steps.agent.sessions import (
    CancelAgentTurnStep,
    DeleteAgentSessionStep,
    ForkAgentSessionStep,
    GetAgentSessionStep,
    ListAgentSessionsStep,
    RenameAgentSessionStep,
    TagAgentSessionStep,
)
from ..steps.common.steps import CommandStep, GetConfigStep, HelpStep, VersionStep
from ..steps.machine.steps import (
    DiagnoseStep,
    ListMachinesStep,
    MachineStatusStep,
    PythonStep,
)
from ..steps.sync.steps import SyncFlushStep, SyncTasksStep, TaskSyncIndexStep
from ..steps.task.catalog import GetTaskDefStep, ListTaskDefsStep
from ..steps.task.query import (
    GetTaskContextStep,
    GetTaskGraphStep,
    GetTaskStatusStep,
    ListTaskDirectoriesStep,
    ListTaskIdsStep,
    ListTaskStatusesStep,
    ReadTaskLogStep,
    StreamTaskStep,
    WaitTaskStep,
)
from ..steps.update.steps import (
    GetUpdateStatusStep,
    RestartServiceStep,
    UpdateFromGitStep,
    UpdateFromPipStep,
)
from ..steps.workspace.steps import DeleteEntriesStep, ListEntriesStep, PreviewFileStep
from ..workspace.core import Workspace
from .context import ApplicationContext

if TYPE_CHECKING:
    from ...task.runtime.catalog import TaskCatalog

APP_PROVIDERS = (
    ClaudeAgentComponent,
    PipelineJob,
    HttpProxyComponent,
    HttpService,
    LocalSyncComponent,
    LocalTaskIndex,
    UpdateManager,
    CommandStep,
    GetConfigStep,
    GetTaskDefStep,
    ListTaskDefsStep,
    SyncTasksStep,
    TaskSyncIndexStep,
    AgentStreamStep,
    CancelAgentTurnStep,
    DeleteAgentSessionStep,
    ForkAgentSessionStep,
    GetAgentSessionStep,
    GetTaskContextStep,
    ListAgentSessionsStep,
    RenameAgentSessionStep,
    TagAgentSessionStep,
    HelpStep,
    VersionStep,
    DiagnoseStep,
    ListMachinesStep,
    MachineStatusStep,
    PythonStep,
    SyncFlushStep,
    GetTaskGraphStep,
    GetTaskStatusStep,
    ListTaskIdsStep,
    ListTaskDirectoriesStep,
    ListTaskStatusesStep,
    ReadTaskLogStep,
    StreamTaskStep,
    WaitTaskStep,
    GetUpdateStatusStep,
    RestartServiceStep,
    UpdateFromGitStep,
    UpdateFromPipStep,
    DeleteEntriesStep,
    ListEntriesStep,
    PreviewFileStep,
)


def compose_application(
    version: str,
    config: dict[str, Any],
    providers: Iterable[type] = (),
    workspace: Workspace | None = None,
    updates: UpdateBackend | None = None,
    task_catalog: TaskCatalog | None = None,
    launch_scheduled: ScheduledLaunch | None = None,
) -> ApplicationContext:
    """Compose built-in providers into an isolated, sealed application context."""
    registry = ProviderRegistry((*APP_PROVIDERS, *providers))
    app_config = ApplicationConfig(**config)
    if app_config.cron and launch_scheduled is None:
        raise ValueError("Cron schedules require a scheduled command launcher")
    configure_logging(
        LoggingConfig(
            log_dir=app_config.log_dir,
            log_to_console=app_config.log_to_console,
            log_to_file=app_config.log_to_file,
            timezone=app_config.timezone,
        ),
    )
    logger = get_logger()
    logger.info(f"Initializing {app_config.app_name} Application v{version}")

    context = ApplicationContext(registry, app_config, workspace, updates, task_catalog)
    for category, group in app_config.components.items():
        context._set_component_group(
            category,
            {name: _instantiate(context, category, name, spec, BaseComponent) for name, spec in group.items()},
        )

    if app_config.cron:
        context._set_component_group(
            "cron",
            {"default": CronComponent(name="cron", app_context=context, launch=launch_scheduled)},
        )

    context._set_jobs(
        {name: _instantiate(context, "job", name, spec, BaseJob) for name, spec in app_config.jobs.items()},
    )
    if app_config.service is not None:
        context._set_service(
            _instantiate(
                context,
                "service",
                "service",
                app_config.service,
                BaseService,
            ),
        )

    component_names = [f"{category}:{name}" for category, group in context.components.items() for name in group]
    logger.info(f"Components ({len(component_names)}): {', '.join(component_names) or '-'}")
    logger.info(f"Jobs ({len(context.jobs)}): {', '.join(context.jobs) or '-'}")
    context.finalize()
    return context


def _instantiate[ComponentT: BaseComponent](
    context: ApplicationContext,
    category: str,
    name: str,
    spec: ComponentConfig,
    expected_base: type[ComponentT],
) -> ComponentT:
    implementation = context.registry.require(category, spec.backend, expected_base)
    options = spec.model_dump(exclude={"backend"}, exclude_unset=True)
    return implementation(
        name=name,
        backend=spec.backend,
        app_context=context,
        **options,
    )
