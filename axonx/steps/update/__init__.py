"""Self-update Job Steps."""

from abc import ABC

from ...components.registry import provider
from ...enums import ComponentEnum
from ..base import BaseStep


class UpdateStep(BaseStep, ABC):
    """Resolve the configured update manager."""

    component_domains = (ComponentEnum.UPDATER,)

    @property
    def updater(self):
        return self._component(ComponentEnum.UPDATER)


@provider("update_from_git_step")
class UpdateFromGitStep(UpdateStep):
    """Discard source changes and update to origin/main."""

    async def execute(self):
        self.response.answer = await self.updater.request("git", self.context.get("force", False))


@provider("update_from_pip_step")
class UpdateFromPipStep(UpdateStep):
    """Upgrade the published backend and Studio packages."""

    async def execute(self):
        self.response.answer = await self.updater.request("pip", self.context.get("force", False))


@provider("get_update_status_step")
class GetUpdateStatusStep(UpdateStep):
    """Read durable update status across service restarts."""

    async def execute(self):
        self.response.answer = self.updater.status(self.context.get("update_id"))
