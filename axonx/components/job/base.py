"""Abstract contract shared by all jobs."""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from copy import deepcopy
from typing import TYPE_CHECKING, Any, cast

from jsonschema.validators import validator_for

from ...constants import CLI_RAW_ARGUMENTS, REMOTE_IP_ARGUMENT
from ...enums import ComponentEnum, JobMode
from ...schema import JobInfo, Response
from ..base import BaseComponent

if TYPE_CHECKING:
    from fastapi import FastAPI


class BaseJob(BaseComponent, ABC):
    """Define lifecycle, invocation, and service capabilities for a job."""

    component_type = ComponentEnum.JOB

    @property
    @abstractmethod
    def mode(self) -> JobMode:
        """Declare how the application manages this job."""

    def __init__(
        self,
        description: str = "",
        parameters: Mapping[str, Any] | None = None,
        enable_serve: bool = True,
        enable_remote: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        if self.kwargs:
            options = ", ".join(sorted(self.kwargs))
            raise TypeError(f"Unsupported {type(self).__name__} options: {options}")
        self.description = description
        schema = parameters if parameters is not None else {"properties": {}}
        self.parameters: dict[str, Any] = deepcopy(dict(schema))
        self.parameters.setdefault("type", "object")
        validator_class = cast(Any, validator_for(self.parameters))
        validator_class.check_schema(self.parameters)
        self.enable_remote = enable_remote
        if self.is_remotely_invocable:
            properties = self.parameters.setdefault("properties", {})
            required = self.parameters.get("required", ())
            if REMOTE_IP_ARGUMENT in properties or REMOTE_IP_ARGUMENT in required:
                raise ValueError(f"{REMOTE_IP_ARGUMENT!r} is a reserved Job parameter")
            properties[REMOTE_IP_ARGUMENT] = {
                "type": "string",
                "description": "Optional IP of a configured remote AxonX node.",
            }
        self._parameter_validator = validator_class(self.parameters)
        self.enable_serve = enable_serve

    @property
    def startup_priority(self) -> int:
        """Start background jobs after jobs that do not schedule their own work."""
        return int(self.mode is JobMode.BACKGROUND)

    @property
    def is_invocable(self) -> bool:
        """Whether callers may execute this job directly."""
        return self.mode is JobMode.ON_DEMAND

    @property
    def is_remotely_invocable(self) -> bool:
        """Whether callers may forward this job to a remote application."""
        return self.is_invocable and self.enable_remote

    @property
    def is_servable(self) -> bool:
        """Whether remote services may expose this job."""
        return self.is_invocable and self.enable_serve

    def mount_http_routes(self, server: "FastAPI") -> None:
        """Optionally mount custom routes on an HTTP service."""
        return None

    async def __call__(self, **kwargs: Any) -> Response:
        """Reject invocation unless a concrete job supplies execution behavior."""
        raise RuntimeError(f"{type(self).__name__} is not directly invocable")

    @property
    def info(self) -> JobInfo:
        """Describe this job's public input and output schemas."""
        return JobInfo(
            name=self.name,
            description=self.description,
            inputSchema=deepcopy(self.parameters),
            outputSchema=Response.model_json_schema(),
        )

    def validate_arguments(self, arguments: Mapping[str, Any]) -> None:
        """Raise ``ValueError`` when arguments violate the job schema."""
        public_arguments = {
            key: value for key, value in arguments.items() if key != CLI_RAW_ARGUMENTS
        }
        try:
            error = next(self._parameter_validator.iter_errors(public_arguments))
        except StopIteration:
            return
        location = ".".join(map(str, error.absolute_path))
        prefix = f"{location}: " if location else ""
        raise ValueError(
            f"Invalid arguments for job {self.name!r}: {prefix}{error.message}"
        )
