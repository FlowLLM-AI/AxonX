"""Own component lifetimes and expose one asynchronous job entry point."""

from __future__ import annotations

import heapq
from pathlib import Path
from typing import Any, TypeVar, cast

from . import __version__
from .components import BaseComponent, R
from .components.client import HttpClient
from .context import ApplicationContext
from .components.job import BaseJob, CronJob
from .constants import REMOTE_IP_ARGUMENT
from .schema import ComponentConfig
from .utils import get_logger

ComponentT = TypeVar("ComponentT", bound=BaseComponent)


class Application(BaseComponent):
    """Build application components and coordinate their async lifetimes."""

    def __init__(self, **config: Any) -> None:
        # Plugins provide tasks only; backends and defaults come from app config.
        registry = R.copy()
        self.context = ApplicationContext(registry, **config)
        logger = get_logger(
            log_to_console=self.context.app_config.log_to_console,
            log_to_file=self.context.app_config.log_to_file,
            force_init=True,
        )
        super().__init__(app_context=self.context)
        logger.info(f"Initializing {self.app_config.app_name} Application v{__version__}")

        self._started_components: list[BaseComponent] = []

        for category, group in self.app_config.components.items():
            self.context.components[category] = {
                name: self._instantiate(category, name, spec, BaseComponent) for name, spec in group.items()
            }
        self.context.jobs = {
            name: self._instantiate("job", name, spec, BaseJob) for name, spec in self.app_config.jobs.items()
        }
        component_names = [
            f"{category}:{name}"
            for category, group in self.context.components.items()
            for name in group
        ]
        logger.info(f"Components ({len(component_names)}): {', '.join(component_names) or '-'}")
        logger.info(f"Jobs ({len(self.context.jobs)}): {', '.join(self.context.jobs) or '-'}")
        registry.freeze()

    def _instantiate(
        self,
        category: str,
        name: str,
        spec: ComponentConfig,
        expected_base: type[ComponentT],
    ) -> ComponentT:
        cls = self.context.registry.get(category, spec.backend)
        if not isinstance(cls, type) or not issubclass(cls, expected_base):
            raise ValueError(f"Unknown {category} backend: {spec.backend}")
        component_cls = cast(type[ComponentT], cls)
        options = spec.model_dump(exclude={"backend"}, exclude_unset=True)
        return component_cls(
            name=name,
            backend=spec.backend,
            app_context=self.context,
            **options,
        )

    def _component_startup_order(self) -> list[BaseComponent]:
        """Order components by declared dependencies and reject invalid graphs."""
        nodes = {
            (category, name): component
            for category, group in self.context.components.items()
            for name, component in group.items()
        }
        positions = {key: index for index, key in enumerate(nodes)}
        in_degree = dict.fromkeys(nodes, 0)
        dependants = {key: [] for key in nodes}
        for key, component in nodes.items():
            for dependency in component.dependencies:
                dependency_key = (dependency.ctype, dependency.name)
                if dependency_key not in nodes:
                    if dependency.optional:
                        continue
                    raise ValueError(
                        f"Component {key[0]}:{key[1]} depends on missing " f"{dependency.ctype}:{dependency.name}",
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
            raise ValueError(
                f"Components unresolved due to circular dependencies: {', '.join(unresolved)}",
            )
        return ordered

    async def _start(self) -> None:
        Path(self.app_config.workspace_dir).expanduser().mkdir(parents=True, exist_ok=True)

        for component in self._component_startup_order():
            await component.start()
            self._started_components.append(component)

        jobs = self.context.jobs.values()
        for job in jobs:
            if not isinstance(job, CronJob):
                await job.start()
                self._started_components.append(job)
        for job in jobs:
            if isinstance(job, CronJob):
                await job.start()
                self._started_components.append(job)

    async def _close(self) -> None:
        self.is_started = False

        errors: list[Exception] = []
        # Jobs stop before their dependencies; cron jobs were started last.
        while self._started_components:
            try:
                await self._started_components.pop().close()
            except Exception as exc:
                errors.append(exc)
        if errors:
            raise ExceptionGroup("Application cleanup failed", errors)

    async def run_job(self, name: str, **kwargs: Any) -> Any:
        """Run a public job."""
        if not self.is_started:
            raise RuntimeError("Application is not running")

        job = self.context.jobs.get(name)
        if job is None:
            raise ValueError(f"Unknown job: {name!r}")
        if isinstance(job, CronJob):
            raise ValueError(f"Job {name!r} is managed in the background")
        if REMOTE_IP_ARGUMENT in kwargs and not job.enable_remote:
            raise ValueError(f"Job {name!r} does not support remote execution")
        job.validate_arguments(kwargs)
        remote_ip = kwargs.pop(REMOTE_IP_ARGUMENT, None)
        if remote_ip is not None:
            node = self.app_config.resolve_remote_node(remote_ip)
            async with HttpClient(host_ip=node.host_ip, host_port=node.host_port) as client:
                return await client.run_job(name, **kwargs)
        return await job(**kwargs)
