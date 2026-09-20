"""Execution contract shared by all Jobs."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Mapping
from copy import deepcopy
from datetime import datetime
from typing import Annotated, Any, Literal, cast

from jsonschema.validators import validator_for
from pydantic import BaseModel, Field, TypeAdapter

from ...constants import REMOTE_IP_ARGUMENT
from ...enums import ComponentEnum
from ..base import BaseComponent


class JobResponse(BaseModel):
    """Canonical result of a Job invocation across every transport."""

    answer: Any = Field(default="", description="response content")
    success: bool = Field(default=True, description="whether succeeded")
    metadata: dict = Field(default_factory=dict, description="metadata")

    def fail(self, error: BaseException) -> JobResponse:
        self.success = False
        self.answer = f"{type(error).__name__}: {error}"
        return self


class JobInfo(BaseModel):
    name: str
    description: str = ""
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]


class JobCatalog(BaseModel):
    items: list[JobInfo] = Field(default_factory=list)
    total: int = 0


class ProgressEvent(BaseModel):
    kind: Literal["progress"] = "progress"
    name: str = Field(min_length=1)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    percentage: float | None = Field(default=None, ge=0, le=100)

    @classmethod
    def from_status(cls, status: Any) -> ProgressEvent:
        return cls.model_validate(status, from_attributes=True)


class LogEvent(BaseModel):
    kind: Literal["log"] = "log"
    content: str = ""
    start_offset: int = 0
    next_offset: int = 0
    file_size: int = 0
    has_more_before: bool = False
    has_more_after: bool = False
    reset: bool = False
    channel: str = "task"

    @classmethod
    def from_chunk(cls, chunk: Any) -> LogEvent:
        return cls.model_validate(chunk, from_attributes=True)


class ArtifactEvent(BaseModel):
    kind: Literal["artifact"] = "artifact"
    path: str
    sha256: str = ""
    size: int = 0
    media_type: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class BackendEvent(BaseModel):
    kind: Literal["backend"] = "backend"
    type_name: str
    message: dict[str, Any]


class ResultEvent(JobResponse):
    kind: Literal["result"] = "result"

    @classmethod
    def from_response(cls, response: JobResponse) -> ResultEvent:
        return cls(answer=response.answer, success=response.success, metadata=response.metadata)

    def response(self) -> JobResponse:
        return JobResponse(answer=self.answer, success=self.success, metadata=self.metadata)


type JobEvent = Annotated[
    ProgressEvent | LogEvent | ArtifactEvent | BackendEvent | ResultEvent,
    Field(discriminator="kind"),
]
JOB_EVENT_ADAPTER: TypeAdapter[JobEvent] = TypeAdapter(JobEvent)


async def fold_events(events: AsyncIterator[JobEvent]) -> JobResponse:
    terminal: ResultEvent | None = None
    async for event in events:
        if isinstance(event, ResultEvent):
            terminal = event
    if terminal is None:
        return JobResponse(answer="Stream produced no terminal result", success=False)
    return terminal.response()


_RESPONSE_SCHEMA = JobResponse.model_json_schema()


def _object_schema(schema: Mapping[str, Any] | None, *, label: str) -> tuple[dict[str, Any], Any]:
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
        requires_auth: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        if self.extra_options:
            options = ", ".join(sorted(self.extra_options))
            raise TypeError(f"Unsupported {type(self).__name__} options: {options}")

        self.description = description
        self.enable_serve = enable_serve
        self.enable_remote = enable_remote
        self.enable_stream = enable_stream
        self.requires_auth = requires_auth
        self.parameters, self._argument_validator = _object_schema(parameters, label="Job parameters")
        if self.enable_remote and REMOTE_IP_ARGUMENT in self.parameters["properties"]:
            raise ValueError(f"{REMOTE_IP_ARGUMENT!r} is reserved for transport targeting")

        injected = dict(self._injected_parameters())
        conflicts = set(self.parameters["properties"]) & injected.keys()
        if conflicts:
            names = ", ".join(sorted(conflicts))
            raise ValueError(f"Job parameters conflict with injected parameters: {names}")
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
            raise ValueError(f"System-owned arguments cannot be supplied by callers: {names}")
        self._raise_first_error(self._argument_validator, arguments, "arguments")

    def validate_system(self, system: Mapping[str, Any]) -> None:
        """Validate framework-owned invocation data."""
        self._raise_first_error(self._injected_validator, system, "system arguments")

    def _raise_first_error(self, validator: Any, value: Mapping[str, Any], label: str) -> None:
        try:
            error = next(validator.iter_errors(dict(value)))
        except StopIteration:
            return
        location = ".".join(map(str, error.absolute_path))
        prefix = f"{location}: " if location else ""
        raise ValueError(f"Invalid {label} for job {self.name!r}: {prefix}{error.message}")

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
