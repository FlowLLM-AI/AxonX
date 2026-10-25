"""Self-update Job Steps."""

from ....common.registry import provider
from ...components.types import ComponentEnum
from ..base import BaseStep


class UpdateStep(BaseStep):
    """Share update admission and configured manager resolution."""

    component_domains = (ComponentEnum.UPDATER,)
    mode: str

    async def execute(self):
        self.response.answer = await self.updater.request(self.mode)

    @property
    def updater(self):
        return self._component(ComponentEnum.UPDATER)


@provider("update_from_git_step")
class UpdateFromGitStep(UpdateStep):
    """Fast-forward the current source branch and rebuild the application."""

    mode = "git"


@provider("update_from_pip_step")
class UpdateFromPipStep(UpdateStep):
    """Upgrade the published backend and Studio packages."""

    mode = "pip"


@provider("restart_service_step")
class RestartServiceStep(UpdateStep):
    """Replace HTTP and cron workers without interrupting scheduled Tasks."""

    mode = "restart"


@provider("get_update_status_step")
class GetUpdateStatusStep(UpdateStep):
    """Read durable update status across service restarts."""

    async def execute(self):
        self.response.answer = {
            **self.updater.status(self.context.get("update_id")),
        }
