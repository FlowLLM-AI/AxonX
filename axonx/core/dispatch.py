"""Validate, log, and route Job invocations."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from typing import TYPE_CHECKING, Any

from ..components.job.base import JobEvent, JobResponse
from ..constants import CLI_RAW_ARGUMENTS
from ..utils import format_log_arguments
from .remote import RemotePreflight, run_remote_job, stream_remote_job

if TYPE_CHECKING:
    from ..components.job.base import BaseJob
    from .context import ApplicationContext


class JobDispatcher:
    """Keep business arguments, system context, and transport targeting separate."""

    def __init__(
        self,
        context: ApplicationContext,
        *,
        remote_preflight: RemotePreflight | None = None,
    ) -> None:
        self._context = context
        self._remote_preflight = remote_preflight

    def _resolve(
        self,
        name: str,
        arguments: Mapping[str, Any] | None,
        system: Mapping[str, Any] | None,
    ) -> tuple[BaseJob, dict[str, Any], dict[str, Any]]:
        job = self._context.jobs.get(name)
        if job is None:
            raise ValueError(f"Unknown job: {name!r}")

        public = dict(arguments or {})
        internal = dict(system or {})
        if CLI_RAW_ARGUMENTS in public:
            raise ValueError(f"Reserved Job argument: {CLI_RAW_ARGUMENTS}")
        job.logger.info(f"Job called: name={name} arguments={format_log_arguments(public)}")
        job.validate_arguments(public)
        job.validate_system(internal)
        return job, public, internal

    async def run(
        self,
        name: str,
        arguments: Mapping[str, Any] | None = None,
        *,
        system: Mapping[str, Any] | None = None,
        remote_ip: str | None = None,
    ) -> JobResponse:
        """Run one Job locally, or explicitly target a configured remote node."""
        job, public, internal = self._resolve(name, arguments, system)
        if remote_ip is None:
            return await job.run(public, internal)
        if not job.is_remotely_invocable:
            raise ValueError(f"Job {name!r} does not support remote execution")
        if internal:
            raise ValueError("System arguments cannot be forwarded to a remote Job")

        node = self._context.app_config.resolve_remote_node(remote_ip)
        return await run_remote_job(
            name,
            public,
            host_ip=node.host_ip,
            host_port=node.host_port,
            token=node.token,
            preflight=self._remote_preflight,
        )

    def stream(
        self,
        name: str,
        arguments: Mapping[str, Any] | None = None,
        *,
        system: Mapping[str, Any] | None = None,
        remote_ip: str | None = None,
    ) -> AsyncIterator[JobEvent]:
        """Validate synchronously, then return the canonical local event stream."""
        job, public, internal = self._resolve(name, arguments, system)
        if not job.is_streamable:
            raise ValueError(f"Job {name!r} does not support streaming")
        if remote_ip is not None:
            if not job.is_remotely_invocable:
                raise ValueError(f"Job {name!r} does not support remote execution")
            if internal:
                raise ValueError("System arguments cannot be forwarded to a remote Job")
            node = self._context.app_config.resolve_remote_node(remote_ip)
            return stream_remote_job(
                name,
                public,
                host_ip=node.host_ip,
                host_port=node.host_port,
                token=node.token,
                preflight=self._remote_preflight,
            )
        return job.stream(public, internal)
