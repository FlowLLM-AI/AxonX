"""Base type for asynchronous job steps."""

from abc import ABC, abstractmethod

from ..components.mixin import ComponentMixin
from ..enums import ComponentEnum


class BaseStep(ComponentMixin, ABC):
    """Run one asynchronous operation against a per-job context."""

    component_type = ComponentEnum.STEP

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.context = None

    def _component(self, component_type):
        return self.get_component(component_type)

    @property
    def machine(self):
        return self._component(ComponentEnum.MACHINE)

    @property
    def plugin(self):
        return self._component(ComponentEnum.PLUGIN)

    @property
    def task_manager(self):
        return self._component(ComponentEnum.TASK_MANAGER)

    @property
    def response(self):
        return self.context.response

    async def __call__(self, context):
        self.context = context
        await self.execute()
        return self.response

    @abstractmethod
    async def execute(self):
        """Perform this step's asynchronous operation."""
