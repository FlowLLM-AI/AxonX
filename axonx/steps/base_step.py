"""An async step is instantiated separately for each job invocation."""

from abc import ABC, abstractmethod

from ..components.component_mixin import ComponentMixin
from ..enumeration import ComponentEnum


class BaseStep(ComponentMixin, ABC):
    """Run one asynchronous operation against a per-job context."""

    component_type = ComponentEnum.STEP

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.context = None

    @property
    def machine(self):
        """Return the default machine component when a step needs host information."""
        return self.get_component(ComponentEnum.MACHINE)

    @property
    def plugin(self):
        """Return the default plugin component."""
        return self.get_component(ComponentEnum.PLUGIN)

    @property
    def task_manager(self):
        """Return the default task manager."""
        return self.get_component(ComponentEnum.TASK_MANAGER)

    @property
    def response(self):
        """Return the current invocation response."""
        return self.context.response

    async def __call__(self, context):
        """Bind the invocation context, execute the step, and return its response."""
        self.context = context
        await self.execute()
        return context.response

    @abstractmethod
    async def execute(self):
        """Perform this step's asynchronous operation."""
