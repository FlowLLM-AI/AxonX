"""Job adapters for command execution, configuration, help and version queries."""

from pathlib import Path

from ..components.job.command import run_command
from ..components.machine.build_info import get_build_info
from ..components.registry import provider
from .base import BaseStep


@provider("command_step")
class CommandStep(BaseStep):
    """Forward stdout/stderr and preserve the child process's exit code."""

    async def execute(self):
        self.response.success, self.response.answer = await run_command(
            self.app_context, self.context["argv"], self.emit
        )


@provider("shell_step")
class ShellStep(BaseStep):
    """Run Bash source in the service environment using shared process ownership."""

    async def execute(self):
        source = self.context["command"]
        if not source.strip():
            raise ValueError("Shell command must not be blank")
        cwd = self.workspace.locate(self.context.get("cwd", "."), external=True)
        if not cwd.is_dir():
            raise ValueError(f"Shell cwd is not a directory: {cwd}")
        self.response.success, self.response.answer = await run_command(
            self.app_context, ("-c", source), self.emit, command_prefix=("/bin/bash",), cwd=cwd
        )


@provider("get_config_step")
class GetConfigStep(BaseStep):
    """Return the running configuration with execution paths resolved here."""

    async def execute(self):
        config = self.app_config.model_dump(mode="json")
        config["workspace_dir"] = str(self.workspace.root)
        config["log_dir"] = str(Path(self.app_config.log_dir).expanduser().resolve())
        self.response.answer = config


@provider("help_step")
class HelpStep(BaseStep):
    """Reuse runtime Job metadata rather than maintaining a command catalog."""

    async def execute(self):
        authenticated = bool(getattr(self.app_context.service, "token", None))
        jobs = self.app_context.public_jobs(authenticated=authenticated)
        name = self.context.get("job")
        if name is not None:
            if name not in jobs:
                raise ValueError(f"Unknown public Job: {name!r}; call help without --job to list available Jobs")
            self.response.answer = {"job": jobs[name].info}
        else:
            self.response.answer = {
                "jobs": [{"name": name, "description": job.description} for name, job in jobs.items()],
            }


@provider("version_step")
class VersionStep(BaseStep):
    """Expose the installed AxonX version."""

    async def execute(self):
        version = get_build_info().version
        self.logger.info(f"[{self.name}] version={version}")
        self.response.answer = version
        self.response.metadata["version"] = version
