"""Assemble providers, inject dependencies, and order the application lifecycle."""

from __future__ import annotations

import heapq
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING

from ..._version import __version__
from ...utils.logging import LoggingConfig, configure_logging, get_logger
from ..components.agent.claude.backend import ClaudeAgentComponent
from ..components.base import BaseComponent
from ..components.cron.base import ScheduledLaunch
from ..components.cron.scheduler import CronComponent
from ..components.job.base import BaseJob
from ..components.job.pipeline import PipelineJob
from ..components.machine.local import LocalMachineComponent
from ..components.proxy.http import HttpProxyComponent
from ..components.registry import ProviderRegistry
from ..components.service.base import BaseService
from ..components.service.http.service import HttpService
from ..components.sync.local import LocalSyncComponent
from ..components.task_index.local import LocalTaskIndex
from ..components.updater.base import UpdateBackend
from ..components.updater.local import LocalUpdaterComponent
from ..config.models import ApplicationConfig, ComponentConfig
from ..steps.agent import (
    AgentStreamStep,
    CancelAgentTurnStep,
    DeleteAgentSessionStep,
    ForkAgentSessionStep,
    GetAgentSessionStep,
    ListAgentSessionsStep,
    RenameAgentSessionStep,
    TagAgentSessionStep,
)
from ..steps.common import CommandStep, GetConfigStep, HelpStep, VersionStep
from ..steps.machine import (
    DiagnoseStep,
    ListMachinesStep,
    MachineStatusStep,
    PythonStep,
)
from ..steps.sync import SyncFlushStep, SyncTasksStep, TaskSyncIndexStep
from ..steps.task import (
    GetTaskContextStep,
    GetTaskDefStep,
    GetTaskGraphStep,
    GetTaskStatusStep,
    ListTaskDefsStep,
    ListTaskDirectoriesStep,
    ListTaskIdsStep,
    ListTaskStatusesStep,
    ReadTaskLogStep,
    StreamTaskStep,
    WaitTaskStep,
)
from ..steps.update import (
    GetUpdateStatusStep,
    RestartServiceStep,
    UpdateFromGitStep,
    UpdateFromPipStep,
)
from ..steps.workspace import DeleteEntriesStep, ListEntriesStep, PreviewFileStep
from ..workspace.core import Workspace
from .context import ApplicationContext

if TYPE_CHECKING:
    from ...task.runtime.catalog import TaskCatalog

APP_PROVIDERS = (
    ClaudeAgentComponent,
    LocalMachineComponent,
    PipelineJob,
    HttpProxyComponent,
    HttpService,
    LocalSyncComponent,
    LocalTaskIndex,
    LocalUpdaterComponent,
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
    app_config: ApplicationConfig,
    *,
    providers: Iterable[type] = (),
    workspace: Workspace | None = None,
    updates: UpdateBackend | None = None,
    task_catalog: TaskCatalog | None = None,
    launch_scheduled: ScheduledLaunch | None = None,
) -> tuple[ApplicationContext, tuple[BaseComponent, ...]]:
    """Return a sealed context and the startup order of every managed object."""
    if app_config.cron and launch_scheduled is None:
        raise ValueError("Cron schedules require a scheduled command launcher")
    reserved = {"job", "service", "step"} & app_config.components.keys()
    if reserved:
        raise ValueError(f"Configure {', '.join(sorted(reserved))} through jobs, service, or Job steps")
    if app_config.cron and app_config.components.get("cron"):
        raise ValueError("Configure Cron schedules through the top-level cron field")
    configure_logging(
        LoggingConfig(
            log_dir=app_config.log_dir,
            log_to_console=app_config.log_to_console,
            log_to_file=app_config.log_to_file,
            timezone=app_config.timezone,
        ),
    )
    logger = get_logger()
    logger.info(f"Initializing {app_config.app_name} Application v{__version__}")

    registry = ProviderRegistry((*APP_PROVIDERS, *providers))
    context = ApplicationContext(registry, app_config, workspace, updates, task_catalog)
    components = {
        category: {name: _instantiate(context, category, name, spec, BaseComponent) for name, spec in group.items()}
        for category, group in app_config.components.items()
    }
    if app_config.cron:
        components["cron"] = {"default": CronComponent(name="cron", app_context=context, launch=launch_scheduled)}
    jobs = {name: _instantiate(context, "job", name, spec, BaseJob) for name, spec in app_config.jobs.items()}
    service = (
        _instantiate(context, "service", "service", app_config.service, BaseService)
        if app_config.service is not None
        else None
    )
    startup_order = _resolve_dependencies(
        {**components, "job": jobs, "service": {"service": service} if service is not None else {}},
    )
    context.finalize(components, jobs, service)

    component_names = [f"{category}:{name}" for category, group in context.components.items() for name in group]
    logger.info(f"Components ({len(component_names)}): {', '.join(component_names) or '-'}")
    logger.info(f"Jobs ({len(context.jobs)}): {', '.join(context.jobs) or '-'}")
    return context, startup_order


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


def _resolve_dependencies(
    components: Mapping[str, Mapping[str, BaseComponent]],
) -> tuple[BaseComponent, ...]:
    """Validate the whole graph before injection; preserve configuration order among ready nodes."""
    nodes = {(category, name): component for category, group in components.items() for name, component in group.items()}
    positions = {key: index for index, key in enumerate(nodes)}
    in_degree = dict.fromkeys(nodes, 0)
    dependants = {key: [] for key in nodes}

    for key, component in nodes.items():
        for dependency in component.dependencies:
            dependency_key = (dependency.component_type, dependency.name)
            if dependency_key not in nodes:
                if not dependency.required:
                    continue
                raise ValueError(
                    f"Component {key[0]}:{key[1]} depends on missing {dependency.component_type}:{dependency.name}",
                )
            if not isinstance(nodes[dependency_key], dependency.expected_type):
                raise TypeError(
                    f"Dependency {dependency.component_type}:{dependency.name} "
                    f"must be a {dependency.expected_type.__name__}",
                )
            in_degree[key] += 1
            dependants[dependency_key].append(key)

    ready = [(positions[key], key) for key, degree in in_degree.items() if degree == 0]
    heapq.heapify(ready)
    ordered = []
    while ready:
        _, key = heapq.heappop(ready)
        ordered.append(nodes[key])
        for dependant in dependants[key]:
            in_degree[dependant] -= 1
            if in_degree[dependant] == 0:
                heapq.heappush(ready, (positions[dependant], dependant))

    if len(ordered) != len(nodes):
        unresolved = [f"{key[0]}:{key[1]}" for key, degree in in_degree.items() if degree]
        raise ValueError("Components unresolved due to circular dependencies: " + ", ".join(unresolved))

    for component in ordered:
        for dependency in component.dependencies:
            setattr(component, dependency.attribute, nodes.get((dependency.component_type, dependency.name)))
    return tuple(ordered)
