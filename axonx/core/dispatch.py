"""Validate, log, and route Job invocations."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from typing import TYPE_CHECKING, Any

from ..components.client.remote import run_remote_job, stream_remote_job
from ..components.job.contracts import JobResponse
from ..components.job.events import JobEvent
from ..constants import CLI_RAW_ARGUMENTS
from ..utils import format_log_arguments

if TYPE_CHECKING:
    from ..components.job.base import BaseJob
    from .context import ApplicationContext


class JobDispatcher:
    """Keep business arguments, system context, and transport targeting separate."""

    def __init__(self, context: ApplicationContext) -> None:
        self._context = context

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
        target: str | None = None,
    ) -> JobResponse:
        """Run one Job locally or connect directly to a configured target."""
        if target is None:
            job, public, internal = self._resolve(name, arguments, system)
            return await job.run(public, internal)
        if system:
            raise ValueError("System arguments cannot be sent to a target service")
        public = dict(arguments or {})
        if CLI_RAW_ARGUMENTS in public:
            raise ValueError(f"Reserved Job argument: {CLI_RAW_ARGUMENTS}")
        configured = self._context.app_config.resolve_target(target)
        return await run_remote_job(
            name,
            public,
            target=configured.address,
            token=configured.token,
        )

    def stream(
        self,
        name: str,
        arguments: Mapping[str, Any] | None = None,
        *,
        system: Mapping[str, Any] | None = None,
        target: str | None = None,
    ) -> AsyncIterator[JobEvent]:
        """Validate synchronously, then return the canonical local event stream."""
        if target is not None:
            if system:
                raise ValueError("System arguments cannot be sent to a target service")
            public = dict(arguments or {})
            if CLI_RAW_ARGUMENTS in public:
                raise ValueError(f"Reserved Job argument: {CLI_RAW_ARGUMENTS}")
            configured = self._context.app_config.resolve_target(target)
            return stream_remote_job(
                name,
                public,
                target=configured.address,
                token=configured.token,
            )
        job, public, internal = self._resolve(name, arguments, system)
        if not job.is_streamable:
            raise ValueError(f"Job {name!r} does not support streaming")
        return job.stream(public, internal)
