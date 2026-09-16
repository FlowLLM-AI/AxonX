"""Build a complete application context from validated configuration."""

from __future__ import annotations

from typing import Any, TypeVar, cast

from ..components.base import BaseComponent
from ..components.job import BaseJob
from ..components.plugin import BasePluginComponent
from ..components.registry import ComponentRegistry
from ..schema import ComponentConfig
from ..utils import get_logger
from .context import ApplicationContext

ComponentT = TypeVar("ComponentT", bound=BaseComponent)


class ApplicationBuilder:
    """Discover contributions and construct one isolated application graph."""

    def __init__(self, registry: ComponentRegistry, version: str, **config: Any) -> None:
        self._registry = registry
        self._version = version
        self._config = config

    def build(self) -> ApplicationContext:
        """Return a fully constructed and immutable application context."""
        context = ApplicationContext(self._registry.copy(), **self._config)
        logger = get_logger(
            log_dir=context.app_config.log_dir,
            log_to_console=context.app_config.log_to_console,
            log_to_file=context.app_config.log_to_file,
            force_init=True,
        )
        logger.info(f"Initializing {context.app_config.app_name} Application v{self._version}")

        self._discover_plugins(context)
        for category, group in context.app_config.components.items():
            if category == "plugin":
                continue
            context.components[category] = {
                name: self._instantiate(context, category, name, spec, BaseComponent) for name, spec in group.items()
            }
        self._merge_plugin_jobs(context)
        context.jobs = {
            name: self._instantiate(context, "job", name, spec, BaseJob)
            for name, spec in context.app_config.jobs.items()
        }

        component_names = [f"{category}:{name}" for category, group in context.components.items() for name in group]
        logger.info(f"Components ({len(component_names)}): {', '.join(component_names) or '-'}")
        logger.info(f"Jobs ({len(context.jobs)}): {', '.join(context.jobs) or '-'}")
        context.registry.freeze()
        return context

    def _discover_plugins(self, context: ApplicationContext) -> None:
        specs = context.app_config.components.get("plugin", {})
        if not specs:
            return
        if len(specs) != 1:
            raise ValueError("Application supports only one plugin manager")
        name, spec = next(iter(specs.items()))
        component = self._instantiate(context, "plugin", name, spec, BasePluginComponent)
        context.components["plugin"] = {name: component}
        component.discover()

    @staticmethod
    def _merge_plugin_jobs(context: ApplicationContext) -> None:
        managers = context.components.get("plugin", {}).values()
        manager = cast(BasePluginComponent | None, next(iter(managers), None))
        plugin_jobs = manager.job_configs() if manager is not None else {}
        conflicts = plugin_jobs.keys() & context.app_config.jobs.keys()
        if conflicts:
            raise ValueError(
                f"Jobs provided by both application config and plugins: {', '.join(sorted(conflicts))}",
            )
        if plugin_jobs:
            context.app_config = context.app_config.model_copy(
                update={"jobs": {**plugin_jobs, **context.app_config.jobs}},
            )

    @staticmethod
    def _instantiate(
        context: ApplicationContext,
        category: str,
        name: str,
        spec: ComponentConfig,
        expected_base: type[ComponentT],
    ) -> ComponentT:
        cls = context.registry.get(category, spec.backend)
        if not isinstance(cls, type) or not issubclass(cls, expected_base):
            raise ValueError(f"Unknown {category} backend: {spec.backend}")
        options = spec.model_dump(exclude={"backend"}, exclude_unset=True)
        return cls(
            name=name,
            backend=spec.backend,
            app_context=context,
            **options,
        )
