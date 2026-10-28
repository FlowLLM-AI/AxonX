"""Self-update Job Steps."""

from ..components.registry import provider
from ..components.updater.base import BaseUpdaterComponent
from .base import BaseStep


class UpdateStep(BaseStep):
    """Share update admission and configured manager resolution."""

    mode: str

    async def execute(self):
        self.response.answer = await self.updater.request(self.mode)

    @property
    def updater(self) -> BaseUpdaterComponent:
        return self.component(BaseUpdaterComponent)


@provider("update_from_git_step")
class UpdateFromGitStep(UpdateStep):
    """Fast-forward the current branch from its upstream and replace the service."""

    mode = "git"


@provider("update_from_pip_step")
class UpdateFromPipStep(UpdateStep):
    """Upgrade the published backend and Studio packages."""

    mode = "pip"


@provider("restart_service_step")
class RestartServiceStep(UpdateStep):
    """Replace the application without interrupting daemon-owned scheduled Tasks."""

    mode = "restart"


@provider("get_update_status_step")
class GetUpdateStatusStep(UpdateStep):
    """Read durable update status across service restarts."""

    async def execute(self):
        self.response.answer = self.updater.status(self.context.get("update_id"))
