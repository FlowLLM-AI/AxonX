"""Own component lifetimes and expose one asynchronous job entry point."""

from __future__ import annotations

import asyncio
import heapq
from collections.abc import Iterator
from pathlib import Path
from typing import Any, TypeVar

from .components import ApplicationContext, BaseComponent
from .components.job import BaseJob
from .plugin import resolve_plugin_runtime
from .schema import ApplicationConfig, ComponentConfig

ComponentT = TypeVar("ComponentT", bound=BaseComponent)


class Application(BaseComponent):
    """Build application components and coordinate their async lifetimes."""

    def __init__(self, **config: Any) -> None:
        runtime = resolve_plugin_runtime(config)
        self.context = ApplicationContext(runtime.registry, **runtime.config)
        super().__init__(app_context=self.context)

        self._started_components: list[BaseComponent] = []
        self._active_job_tasks: set[asyncio.Task[Any]] = set()
        self._accepting = False

        for category, group in self.config.components.items():
            self.context.components[category] = {
                name: self._instantiate(category, name, spec, BaseComponent) for name, spec in group.items()
            }
        self.context.jobs = {
            name: self._instantiate("job", name, spec, BaseJob) for name, spec in self.config.jobs.items()
        }
        runtime.registry.freeze()

    @property
    def config(self) -> ApplicationConfig:
        """Return the validated application configuration."""
        return self.context.app_config

    def _instantiate(
        self,
        category: str,
        name: str,
        spec: ComponentConfig,
        expected_base: type[ComponentT],
    ) -> ComponentT:
        cls = self.context.registry.get(category, spec.backend)
        if cls is None or not issubclass(cls, expected_base):
            raise ValueError(f"Unknown {category} backend: {spec.backend}")
        options = spec.model_dump(exclude={"backend"}, exclude_unset=True)
        return cls(
            name=name,
            backend=spec.backend,
            app_context=self.context,
            **options,
        )

    def _iter_startup_components(self) -> Iterator[BaseComponent]:
        yield from self._component_startup_order()

        jobs = self.context.jobs.values()
        yield from (job for job in jobs if not job.runs_in_background)

        # Background runners may execute immediately, so start them only after
        # every dependency and directly callable job is ready.
        yield from (job for job in jobs if job.runs_in_background)

    def _component_startup_order(self) -> list[BaseComponent]:
        """Order components by declared dependencies and reject invalid graphs."""
        nodes = {
            (category, name): component
            for category, group in self.context.components.items()
            for name, component in group.items()
        }
        in_degree = dict.fromkeys(nodes, 0)
        dependants = {key: [] for key in nodes}
        for key, component in nodes.items():
            for dependency in component.dependencies:
                dependency_key = (dependency.ctype, dependency.name)
                if dependency_key not in nodes:
                    if dependency.optional:
                        continue
                    raise ValueError(
                        f"Component {key[0]}:{key[1]} depends on missing "
                        f"{dependency.ctype}:{dependency.name}",
                    )
                in_degree[key] += 1
                dependants[dependency_key].append(key)

        ready = [key for key, degree in in_degree.items() if degree == 0]
        heapq.heapify(ready)
        ordered = []
        while ready:
            key = heapq.heappop(ready)
            ordered.append(nodes[key])
            for dependant in dependants[key]:
                in_degree[dependant] -= 1
                if in_degree[dependant] == 0:
                    heapq.heappush(ready, dependant)
        if len(ordered) != len(nodes):
            unresolved = [f"{key[0]}:{key[1]}" for key, degree in in_degree.items() if degree]
            raise ValueError(f"Circular component dependency: {', '.join(unresolved)}")
        return ordered

    async def _start(self) -> None:
        Path(self.config.workspace_dir).expanduser().mkdir(parents=True, exist_ok=True)
        for component in self._iter_startup_components():
            await component.start()
            self._started_components.append(component)
        self._accepting = True

    async def _close(self) -> None:
        self._accepting = False

        shutdown_task = asyncio.current_task()
        active_tasks = [task for task in self._active_job_tasks if task is not shutdown_task]
        for task in active_tasks:
            task.cancel()
        await asyncio.gather(*active_tasks, return_exceptions=True)

        errors: list[Exception] = []
        # Close in reverse startup order so dependants stop before dependencies.
        while self._started_components:
            try:
                await self._started_components.pop().close()
            except Exception as exc:
                errors.append(exc)
        if errors:
            raise ExceptionGroup("Application cleanup failed", errors)

    async def run_job(self, name: str, **kwargs: Any) -> Any:
        """Run a public job and track its calling task for application shutdown.

        Closing the application cancels tasks currently awaiting this method.
        """
        if not self._accepting:
            raise RuntimeError("Application is not running")

        job = self.context.jobs.get(name)
        if job is None:
            raise ValueError(f"Unknown job: {name!r}")
        if job.runs_in_background:
            raise ValueError(f"Job {name!r} is managed in the background")
        job.validate_arguments(kwargs)

        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("Job execution requires an asyncio task")

        self._active_job_tasks.add(task)
        try:
            return await job(**kwargs)
        finally:
            self._active_job_tasks.discard(task)
