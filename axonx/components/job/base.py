"""Execution contract shared by all Jobs."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Mapping
from copy import deepcopy
from typing import Any, cast

from jsonschema.validators import validator_for

from ...constants import REMOTE_IP_ARGUMENT
from ...enums import ComponentEnum
from ..base import BaseComponent
from .contracts import JobCatalog, JobInfo, JobResponse
from .events import (
    JOB_EVENT_ADAPTER,
    AgentBlockPatch,
    AgentMessageEvent,
    ArtifactEvent,
    JobEvent,
    LogEvent,
    ProgressEvent,
    ResultEvent,
    fold_events,
)

_RESPONSE_SCHEMA = JobResponse.model_json_schema()


def _object_schema(
    schema: Mapping[str, Any] | None, *, label: str
) -> tuple[dict[str, Any], Any]:
    """Validate and compile one JSON object schema."""
    value: dict[str, Any] = deepcopy(dict(schema or {}))
    value.setdefault("type", "object")
    validator_class = cast(Any, validator_for(value))
    try:
        validator_class.check_schema(value)
    except Exception as exc:
        raise ValueError(f"Invalid {label} schema: {exc}") from exc
    if value["type"] != "object":
        raise ValueError(f"{label} schema must describe an object")
    value.setdefault("properties", {})
    return value, validator_class(value)


class BaseJob(BaseComponent, ABC):
    """Validate arguments and expose one canonical event-stream execution API."""

    component_type = ComponentEnum.JOB

    def __init__(
        self,
        description: str = "",
        parameters: Mapping[str, Any] | None = None,
        enable_serve: bool = True,
        enable_remote: bool = True,
        enable_stream: bool = True,
        requires_auth: bool = True,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)

        self.description = description
        self.enable_serve = enable_serve
        self.enable_remote = enable_remote
        self.enable_stream = enable_stream
        self.requires_auth = requires_auth
        self.parameters, self._argument_validator = _object_schema(
            parameters, label="Job parameters"
        )
        if self.enable_remote and REMOTE_IP_ARGUMENT in self.parameters["properties"]:
            raise ValueError(
                f"{REMOTE_IP_ARGUMENT!r} is reserved for transport targeting"
            )

        injected = dict(self._injected_parameters())
        conflicts = set(self.parameters["properties"]) & injected.keys()
        if conflicts:
            names = ", ".join(sorted(conflicts))
            raise ValueError(
                f"Job parameters conflict with injected parameters: {names}"
            )
        injected_schema = {
            "type": "object",
            "properties": deepcopy(injected),
            "additionalProperties": False,
        }
        self._injected_schema, self._injected_validator = _object_schema(
            injected_schema,
            label="injected Job parameters",
        )

    def _injected_parameters(self) -> Mapping[str, Any]:
        """Return system-owned context fields required by this Job."""
        return {}

    @property
    def injected_parameters(self) -> Mapping[str, Any]:
        """Return a defensive copy of system-owned parameter definitions."""
        return deepcopy(self._injected_schema["properties"])

    @property
    def is_servable(self) -> bool:
        return self.enable_serve

    @property
    def is_remotely_invocable(self) -> bool:
        return self.enable_remote

    @property
    def is_streamable(self) -> bool:
        return self.enable_stream

    def validate_arguments(self, arguments: Mapping[str, Any]) -> None:
        """Validate caller-owned business arguments."""
        conflicts = set(arguments) & self._injected_schema["properties"].keys()
        if conflicts:
            names = ", ".join(sorted(conflicts))
            raise ValueError(
                f"System-owned arguments cannot be supplied by callers: {names}"
            )
        self._raise_first_error(self._argument_validator, arguments, "arguments")

    def validate_system(self, system: Mapping[str, Any]) -> None:
        """Validate framework-owned invocation data."""
        self._raise_first_error(self._injected_validator, system, "system arguments")

    def _raise_first_error(
        self, validator: Any, value: Mapping[str, Any], label: str
    ) -> None:
        try:
            error = next(validator.iter_errors(dict(value)))
        except StopIteration:
            return
        location = ".".join(map(str, error.absolute_path))
        prefix = f"{location}: " if location else ""
        raise ValueError(
            f"Invalid {label} for job {self.name!r}: {prefix}{error.message}"
        )

    @abstractmethod
    def stream(
        self,
        arguments: Mapping[str, Any],
        system: Mapping[str, Any],
    ) -> AsyncIterator[JobEvent]:
        """Execute this Job as an event stream."""
        raise NotImplementedError

    async def run(
        self,
        arguments: Mapping[str, Any],
        system: Mapping[str, Any],
    ) -> JobResponse:
        """Fold the canonical event stream into its terminal response."""
        return await fold_events(self.stream(arguments, system))

    @property
    def info(self) -> JobInfo:
        """Describe only caller-owned inputs, never framework-owned fields."""
        return JobInfo(
            name=self.name,
            description=self.description,
            input_schema=deepcopy(self.parameters),
            output_schema=deepcopy(_RESPONSE_SCHEMA),
        )
