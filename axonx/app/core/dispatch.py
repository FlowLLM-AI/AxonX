"""Validate, log, and route Job invocations."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from typing import TYPE_CHECKING, Any

from ...client import http as client
from ...client.events import JobEvent
from ...client.models import JobResponse
from ...utils.logging import format_log_arguments

if TYPE_CHECKING:
    from ..components.job.base import BaseJob
    from ..config.models import TargetConfig
    from .context import ApplicationContext

_MAINTENANCE_JOBS = frozenset({"get_update_status", "version"})


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
        if self._context.metadata.get("maintenance"):
            argv = (arguments or {}).get("argv")
            cli_query = name == "cli" and isinstance(argv, list) and argv and argv[0] in _MAINTENANCE_JOBS
            if name not in _MAINTENANCE_JOBS and not cli_query:
                raise ValueError("Service is in maintenance for self-update")
        job = self._context.jobs.get(name)
        if job is None:
            raise ValueError(f"Unknown job: {name!r}")

        public = dict(arguments or {})
        internal = dict(system or {})
        job.logger.info(f"Job called: name={name} arguments={format_log_arguments(public)}")
        job.validate_arguments(public)
        job.validate_system(internal)
        return job, public, internal

    def _remote_target(self, target: str, system: Mapping[str, Any] | None) -> TargetConfig:
        if system:
            raise ValueError("System arguments cannot be sent to a target service")
        return self._context.app_config.resolve_target(target)

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
        configured = self._remote_target(target, system)
        return await client.run_remote_job(
            name,
            dict(arguments or {}),
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
        """Validate synchronously, then return a local or remote event stream."""
        if target is not None:
            configured = self._remote_target(target, system)
            return client.stream_remote_job(
                name,
                dict(arguments or {}),
                target=configured.address,
                token=configured.token,
            )
        job, public, internal = self._resolve(name, arguments, system)
        if not job.enable_stream:
            raise ValueError(f"Job {name!r} does not support streaming")
        return job.stream(public, internal)
