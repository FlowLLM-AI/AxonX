"""Compose one complete, isolated application runtime."""

# Internal wiring intentionally uses private runtime hooks.
# pylint: disable=protected-access

from __future__ import annotations

from typing import Any

from ...common.logging import LoggingConfig, configure_logging, get_logger
from ...common.registry import ProviderRegistry
from ..components.base import BaseComponent
from ..components.job import BaseJob
from ..components.service import BaseService
from ..config import ApplicationConfig, ComponentConfig
from .context import ApplicationContext


def compose_application(
    registry: ProviderRegistry,
    version: str,
    config: dict[str, Any],
) -> ApplicationContext:
    """Discover contributions and return a sealed application context."""
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

    context = ApplicationContext(registry, app_config)
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
