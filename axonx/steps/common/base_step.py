"""Base type for asynchronous job steps."""

from abc import ABC, abstractmethod

from ...components.component_mixin import ComponentMixin
from ...enumeration import ComponentEnum


class BaseStep(ComponentMixin, ABC):
    """Run one asynchronous operation against a per-job context."""

    component_type = ComponentEnum.STEP

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.context = None

    def _component(self, component_type):
        return self.get_component(component_type)

    machine = property(lambda self: self._component(ComponentEnum.MACHINE))
    plugin = property(lambda self: self._component(ComponentEnum.PLUGIN))
    task_manager = property(lambda self: self._component(ComponentEnum.TASK_MANAGER))
    response = property(lambda self: self.context.response)

    async def __call__(self, context):
        self.context = context
        await self.execute()
        return self.response

    @abstractmethod
    async def execute(self):
        """Perform this step's asynchronous operation."""
