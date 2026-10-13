"""Self-update Job Steps."""

from ...components.registry import provider
from ...enums import ComponentEnum
from ..base import BaseStep


class UpdateStep(BaseStep):
    """Share update admission and configured manager resolution."""

    component_domains = (ComponentEnum.UPDATER,)
    mode: str

    async def execute(self):
        self.response.answer = await self.updater.request(self.mode, self.context.get("force", False))

    @property
    def updater(self):
        return self._component(ComponentEnum.UPDATER)


@provider("update_from_git_step")
class UpdateFromGitStep(UpdateStep):
    """Discard source changes and update to origin/main."""

    mode = "git"


@provider("update_from_pip_step")
class UpdateFromPipStep(UpdateStep):
    """Upgrade the published backend and Studio packages."""

    mode = "pip"


@provider("restart_service_step")
class RestartServiceStep(UpdateStep):
    """Restart using the original arguments without changing installed files."""

    mode = "restart"


@provider("get_update_status_step")
class GetUpdateStatusStep(UpdateStep):
    """Read durable update status across service restarts."""

    async def execute(self):
        self.response.answer = {
            **self.updater.status(self.context.get("update_id")),
            "restart_blockers": await self.updater.restart_blockers(),
        }
