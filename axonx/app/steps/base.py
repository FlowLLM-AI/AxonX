"""Base type for asynchronous job steps."""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, ClassVar

from ..components.base import ComponentBase
from ..components.component_type import ComponentType
from ..components.job.events import JobEvent


class BaseStep(ComponentBase, ABC):
    """Run one asynchronous operation against a per-job context."""

    component_type = ComponentType.STEP

    #: Component-backed steps opt in to exactly the domains they use.
    component_domains: ClassVar[tuple[ComponentType, ...]] = ()

    #: System-owned context fields this Step requires, by name and JSON schema.
    #: PipelineJob validates them separately, so they never enter the caller's
    #: public Job schema.
    injected_parameters: ClassVar[Mapping[str, Any]] = {}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.context = None
        self._emit: Callable[[JobEvent], Awaitable[None]] | None = None

    def _component(self, component_type: ComponentType):
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
        return self._component(ComponentType.AGENT)

    @property
    def sync(self):
        """Return the workspace sync backend this step drives."""
        return self._component(ComponentType.SYNC)

    @property
    def task_index(self):
        """Return the Task index this step drives."""
        return self._component(ComponentType.TASK_INDEX)

    @property
    def response(self):
        """Return the response this step writes its outcome to."""
        return self.context.response

    async def __call__(
        self,
        context,
        emit: Callable[[JobEvent], Awaitable[None]] | None = None,
    ):
        """Run this step with an invocation-scoped event sink."""
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
