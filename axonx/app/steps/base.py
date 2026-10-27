"""Base type for asynchronous job steps."""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, ClassVar

from ...client.events import JobEvent
from ..components.base import BaseComponent, ComponentBase
from ..components.models import ComponentType


class BaseStep(ComponentBase, ABC):
    """Run one asynchronous operation against a per-job context."""

    component_type = ComponentType.STEP
    component_domains: ClassVar[tuple[ComponentType, ...]] = ()

    #: System-owned context fields this Step requires, by name and JSON schema.
    #: PipelineJob validates them separately, so they never enter the caller's
    #: public Job schema.
    injected_parameters: ClassVar[Mapping[str, Any]] = {}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._component_names = {domain: self.kwargs.pop(domain.value, "default") for domain in self.component_domains}
        self.context = None
        self._emit: Callable[[JobEvent], Awaitable[None]] | None = None

    def component[ComponentT: BaseComponent](self, base_cls: type[ComponentT]) -> ComponentT:
        """Resolve a declared domain and verify its configured implementation."""
        domain = base_cls.component_type
        name = self._component_names[domain]
        try:
            component = self._require_context().components[domain][name]
        except KeyError as exc:
            raise ValueError(f"Unknown {domain} component: {name!r}") from exc
        if not isinstance(component, base_cls):
            raise TypeError(f"Component {domain}:{name} must be a {base_cls.__name__}")
        return component

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
            self.context = None

    async def emit(self, event: JobEvent) -> None:
        """Publish one event, waiting when the Job's bounded buffer is full."""
        if self._emit is not None:
            await self._emit(event)

    @abstractmethod
    async def execute(self):
        """Perform this step's asynchronous operation."""
