"""Validate, log, and route public Job invocations."""

from __future__ import annotations

from typing import Any

from ..components.client import HttpClient
from ..constants import REMOTE_IP_ARGUMENT
from ..utils import format_log_arguments
from .context import ApplicationContext


class JobDispatcher:
    """Dispatch Jobs locally or to a configured remote node."""

    def __init__(self, context: ApplicationContext) -> None:
        self._context = context

    async def run(self, name: str, **kwargs: Any) -> Any:
        """Validate and invoke one public Job."""
        job = self._context.jobs.get(name)
        if job is None:
            raise ValueError(f"Unknown job: {name!r}")
        if not job.is_invocable:
            raise ValueError(f"Job {name!r} does not support direct invocation in {job.mode.value!r} mode")
        if REMOTE_IP_ARGUMENT in kwargs and not job.is_remotely_invocable:
            raise ValueError(f"Job {name!r} does not support remote execution")

        job.logger.info(f"Job called: name={name} arguments={format_log_arguments(kwargs)}")
        job.validate_arguments(kwargs)
        remote_ip = kwargs.pop(REMOTE_IP_ARGUMENT, None)
        if remote_ip is None:
            return await job(**kwargs)

        node = self._context.app_config.resolve_remote_node(remote_ip)
        async with HttpClient(host_ip=node.host_ip, host_port=node.host_port) as client:
            return await client.run_job(name, **kwargs)
