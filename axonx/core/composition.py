"""Compose one complete, isolated application runtime."""

from __future__ import annotations

from typing import Any

from ..components.base import BaseComponent
from ..components.job import BaseJob
from ..components.registry import ProviderRegistry
from ..components.scheduler import BaseScheduler
from ..components.service import BaseService
from ..config import ApplicationConfig, ComponentConfig, JobConfig
from ..plugin_kit.runtime import load_plugin_providers
from ..plugin_kit.verification import verify_remote_submission
from ..utils import LoggingConfig, configure_logging, get_logger
from .context import ApplicationContext


def compose_application(
    registry: ProviderRegistry,
    version: str,
    config: dict[str, Any],
) -> ApplicationContext:
    """Discover contributions and return a sealed application context."""
    context = ApplicationContext(registry, **config)
    configure_logging(
        LoggingConfig(
            log_dir=context.app_config.log_dir,
            log_to_console=context.app_config.log_to_console,
            log_to_file=context.app_config.log_to_file,
        )
    )
    logger = get_logger()
    logger.info(
        f"Initializing {context.app_config.app_name} Application v{version}"
    )

    plugin_jobs = load_plugin_providers(context.app_config, registry)
    for category, group in context.app_config.components.items():
        context.components[category] = {
            name: _instantiate(context, category, name, spec, BaseComponent)
            for name, spec in group.items()
        }

    context.app_config = _merge_plugin_jobs(context.app_config, plugin_jobs)
    context.jobs = {
        name: _instantiate(context, "job", name, spec, BaseJob)
        for name, spec in context.app_config.jobs.items()
    }
    context.schedulers = {
        name: _instantiate(context, "scheduler", name, spec, BaseScheduler)
        for name, spec in context.app_config.schedules.items()
    }
    if context.app_config.service is not None:
        context.service = _instantiate(
            context,
            "service",
            "service",
            context.app_config.service,
            BaseService,
        )

    component_names = [
        f"{category}:{name}"
        for category, group in context.components.items()
        for name in group
    ]
    logger.info(
        f"Components ({len(component_names)}): {', '.join(component_names) or '-'}"
    )
    logger.info(f"Jobs ({len(context.jobs)}): {', '.join(context.jobs) or '-'}")
    logger.info(
        f"Schedules ({len(context.schedulers)}): "
        f"{', '.join(context.schedulers) or '-'}"
    )
    context.finalize(remote_preflight=verify_remote_submission)
    return context


def _merge_plugin_jobs(
    config: ApplicationConfig,
    plugin_jobs: dict[str, JobConfig],
) -> ApplicationConfig:
    conflicts = plugin_jobs.keys() & config.jobs.keys()
    if conflicts:
        raise ValueError(
            "Jobs provided by both application config and plugins: "
            + ", ".join(sorted(conflicts)),
        )
    if not plugin_jobs:
        return config
    return config.model_copy(update={"jobs": {**plugin_jobs, **config.jobs}})


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
