"""Compose one complete, isolated application runtime."""

# Internal wiring intentionally uses private runtime hooks.
# pylint: disable=protected-access

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ..workspace import Workspace

from ...common.logging import LoggingConfig, configure_logging, get_logger
from ..registry import ProviderRegistry
from ..components.agent.claude import ClaudeAgentComponent
from ..components.base import BaseComponent
from ..components.job.base import BaseJob
from ..components.job.pipeline import PipelineJob
from ..components.proxy import HttpProxyComponent
from ..components.service import HttpService
from ..components.service.base import BaseService
from ..components.sync.local import LocalSyncComponent
from ..components.task_index import LocalTaskIndex
from ..components.updater import UpdateManager
from ..components.updater.manager import UpdateBackend
from ..config.models import ApplicationConfig, ComponentConfig
from ..steps.agent import (
    AgentStreamStep,
    CancelAgentTurnStep,
    DeleteAgentSessionStep,
    ForkAgentSessionStep,
    GetAgentSessionStep,
    GetTaskContextStep,
    ListAgentSessionsStep,
    RenameAgentSessionStep,
    TagAgentSessionStep,
)
from ..steps.common import CommandStep, HelpStep, VersionStep
from ..steps.machine.steps import DiagnoseStep, ListMachinesStep, MachineStatusStep, PythonStep
from ..steps.studio import ListStudioPagesStep
from ..steps.sync import SyncFlushStep, SyncTasksStep, TaskSyncIndexStep
from ..steps.task import (
    GetTaskDefinitionStep,
    ListInstalledTaskDefinitionsStep,
    GetTaskGraphStep,
    GetTaskStatusStep,
    ListTaskIdsStep,
    ListTaskDirectoriesStep,
    ListTaskStatusesStep,
    ReadTaskLogStep,
    StreamTaskStep,
    WaitTaskStep,
)
from ..steps.update import GetUpdateStatusStep, RestartServiceStep, UpdateFromGitStep, UpdateFromPipStep
from ..steps.workspace import DeleteEntriesStep, ListEntriesStep, PreviewFileStep
from .context import ApplicationContext

APP_PROVIDERS = (
    ClaudeAgentComponent,
    PipelineJob,
    HttpProxyComponent,
    HttpService,
    LocalSyncComponent,
    LocalTaskIndex,
    UpdateManager,
    CommandStep,
    GetTaskDefinitionStep,
    ListInstalledTaskDefinitionsStep,
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
    ListStudioPagesStep,
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
) -> ApplicationContext:
    """Compose built-in providers into an isolated, sealed application context."""
    registry = ProviderRegistry((*APP_PROVIDERS, *providers))
    app_config = ApplicationConfig(**config)
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

    context = ApplicationContext(registry, app_config, workspace, updates)
    for category, group in app_config.components.items():
        context._set_component_group(
            category,
            {name: _instantiate(context, category, name, spec, BaseComponent) for name, spec in group.items()},
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
