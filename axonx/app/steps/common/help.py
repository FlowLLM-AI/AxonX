"""Discover the selected service's public Job contracts."""

from ....common.registry import provider
from ..base import BaseStep


@provider("help_step")
class HelpStep(BaseStep):
    """Reuse runtime Job metadata rather than maintaining a command catalog."""

    async def execute(self):
        authenticated = bool(getattr(self.app_context.service, "token", None))
        jobs = {name: job for name, job in self.app_context.jobs.items() if job.is_public(authenticated=authenticated)}
        name = self.context.get("job")
        if name is not None:
            if name not in jobs:
                raise ValueError(f"Unknown public Job: {name!r}; call help without --job to list available Jobs")
            self.response.answer = {"job": jobs[name].info}
        else:
            self.response.answer = {
                "jobs": [{"name": name, "description": jobs[name].description} for name in sorted(jobs)],
            }
