"""Base type for asynchronous job steps."""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, ClassVar

from ..components.base import ComponentBase
from ..components.job.events import JobEvent
from ..enums import ComponentEnum


class BaseStep(ComponentBase, ABC):
    """Run one asynchronous operation against a per-job context."""

    component_type = ComponentEnum.STEP

    #: Component-backed steps opt in to exactly the domains they use. Keeping
    #: this empty makes irrelevant options fail as configuration errors.
    component_domains: ClassVar[tuple[ComponentEnum, ...]] = ()

    #: System-owned context fields this Step requires, by name and JSON schema.
    #: PipelineJob validates them separately, so they never enter the caller's
    #: public Job schema.
    injected_parameters: ClassVar[Mapping[str, Any]] = {}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.context = None
        self._emit: Callable[[JobEvent], Awaitable[None]] | None = None

    def _component(self, component_type: ComponentEnum):
        """Return the component of one domain this step was configured to drive."""
        name = self._component_names[component_type]
        try:
            return self.get_component(component_type, name)
        except KeyError as exc:
            # Named, because the raw lookup reports only the key that missed.
            raise ValueError(f"Unknown {component_type} component: {name!r}") from exc

    @property
    def agent_wrapper(self):
        """Return the agent backend this step drives."""
        return self._component(ComponentEnum.AGENT)

    @property
    def task_manager(self):
        """Return the task manager this step drives."""
        return self._component(ComponentEnum.TASK_MANAGER)

    @property
    def sync(self):
        """Return the workspace sync backend this step drives."""
        return self._component(ComponentEnum.SYNC)

    @property
    def task_repository(self):
        """Return the Task repository this step drives."""
        return self._component(ComponentEnum.TASK_REPOSITORY)

    @property
    def response(self):
        """Return the response this step writes its outcome to."""
        return self.context.response

    async def __call__(
        self,
        context,
        emit: Callable[[JobEvent], Awaitable[None]] | None = None,
    ):
        """Run this step, publishing any events it emits to ``emit``.

        ``emit`` is an invocation parameter rather than job configuration, so a
        step's schema never grows a field for it. A step that writes only to
        ``self.response`` — which is all of them today — ignores it entirely.
        """
        self.context = context
        self._emit = emit
        try:
            await self.execute()
            return self.response
        finally:
            self._emit = None

    async def emit(self, event: JobEvent) -> None:
        """Publish one event, waiting when the Job's bounded buffer is full."""
        if self._emit is not None:
            await self._emit(event)

    @abstractmethod
    async def execute(self):
        """Perform this step's asynchronous operation."""
