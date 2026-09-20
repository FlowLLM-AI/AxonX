"""Claude Code SDK agent backend."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import aclosing
from dataclasses import asdict, fields, is_dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ...constants import AGENT_DEPTH_ARGUMENT
from ..job.contracts import JobResponse
from ..job.events import BackendEvent, JobEvent, ResultEvent
from ..registry import provider
from .base import BaseAgentComponent
from .tools import JobToolServer

if TYPE_CHECKING:
    from claude_agent_sdk import ClaudeAgentOptions, ResultMessage


@lru_cache(maxsize=1)
def _option_names() -> frozenset[str]:
    """Return the SDK option names this component forwards verbatim.

    Read off the SDK's own dataclass, so the configuration surface tracks the
    installed SDK instead of a copy of it that has to be kept in step. Cached
    because every turn consults it.
    """
    from claude_agent_sdk import ClaudeAgentOptions

    return frozenset(field.name for field in fields(ClaudeAgentOptions))


def _to_response(result: ResultMessage) -> JobResponse:
    """Fold a terminal result message into an AxonX job response.

    Structured output is the answer when a successful turn requested it. For a
    failed turn, the CLI's result text or errors remain the answer. Every other
    terminal field is retained as metadata so SDK additions are not silently
    discarded here.
    """
    payload = asdict(result)
    success = not payload.pop("is_error")
    text = payload.pop("result")
    structured = payload.pop("structured_output")
    fallback = text or "; ".join(payload.get("errors") or ())
    answer = structured if success and structured is not None else fallback
    return JobResponse(answer=answer, success=success, metadata=payload)


def _sdk_value(value: Any) -> Any:
    """Serialize an SDK value without losing nested block class names."""
    if is_dataclass(value) and not isinstance(value, type):
        return {
            "type_name": type(value).__name__,
            **{
                field.name: _sdk_value(getattr(value, field.name))
                for field in fields(value)
            },
        }
    if isinstance(value, Mapping):
        return {key: _sdk_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sdk_value(item) for item in value]
    return value


def _message_payload(message: Any) -> dict[str, Any]:
    """Serialize one SDK message, tagging every nested content block."""
    return {
        field.name: _sdk_value(getattr(message, field.name))
        for field in fields(message)
    }


@provider("claude")
class ClaudeAgentComponent(BaseAgentComponent):
    """Run one agent turn per call on a fresh Claude Code CLI process.

    Every ``ClaudeAgentOptions`` field is a valid component option, so the
    configuration stays a thin declaration over the SDK instead of a parallel
    vocabulary that has to be translated field by field.
    """

    SDK_PACKAGE = "claude-agent-sdk"

    def __init__(
        self, job_tools: Sequence[str] = (), state_dir: str = "agent", **kwargs
    ) -> None:
        super().__init__(**kwargs)
        if isinstance(job_tools, str):
            raise TypeError("job_tools must be a sequence of Job names, not a string")
        known = _option_names()
        self.options = {
            name: value for name, value in self.kwargs.items() if name in known
        }
        self.job_tools = tuple(job_tools)
        self.state_dir = state_dir
        self._job_tool_server: JobToolServer | None = None

    @classmethod
    def _known_options(
        cls, options: Mapping[str, Any], *, reserved: frozenset[str] = frozenset()
    ) -> dict:
        """Return the SDK options among ``options``, rejecting every other name.

        ``reserved`` names arguments passed by the event protocol rather than the
        SDK. Component construction is intentionally more permissive: options it
        does not consume remain available through ``self.kwargs``.
        """
        known = _option_names()
        unknown = sorted(set(options) - known - reserved)
        if unknown:
            raise ValueError(
                f"Unknown agent options for {cls.__name__}: {', '.join(unknown)}"
            )
        return {name: value for name, value in options.items() if name in known}

    @property
    def cwd(self) -> Path:
        """Return the working directory shared by the agent's shell and file tools."""
        return self._resolve_cwd(self.options.get("cwd"))

    def _resolve_cwd(self, configured: str | None) -> Path:
        """Resolve one configured working directory against the workspace.

        Absent means the workspace root, so the agent sees Task artifacts; a
        relative value is read as workspace-relative.
        """
        if not configured:
            return self.workspace_path
        cwd = Path(configured).expanduser()
        return cwd if cwd.is_absolute() else self.workspace_path / cwd

    @property
    def config_dir(self) -> Path | None:
        """Return the workspace-local ``CLAUDE_CONFIG_DIR``, or None when shared.

        Claude Code keeps its sessions and its own state under this directory.
        Isolating it below the workspace, one directory per component, keeps a
        service from writing into the operator's ``~/.claude`` — and from reading
        the settings there. It is None when ``state_dir`` is empty, which opts
        back into that shared home directory (what a ``claude login`` credential
        needs), or when the environment already names one explicitly.
        """
        environment = {**self.subprocess_environment, **(self.options.get("env") or {})}
        if not self.state_dir or "CLAUDE_CONFIG_DIR" in environment:
            return None
        workspace = self.workspace_path.resolve(strict=False)
        config_dir = (workspace / self.state_dir / self.name).resolve(strict=False)
        if not config_dir.is_relative_to(workspace):
            raise ValueError(
                "state_dir and component name must resolve inside the workspace"
            )
        return config_dir

    @property
    def subprocess_environment(self) -> dict[str, str]:
        """Return environment variables handed to the agent's CLI process.

        Mirrors how ``LocalTaskManager`` seeds Task subprocesses, so ``.env``
        values such as ``ANTHROPIC_AUTH_TOKEN`` reach the agent through the same
        path they reach Tasks.
        """
        if self.app_context is None:
            return {}
        return dict(self.app_config.environment)

    async def compact_session(self, session_id: str) -> None:
        """Compact one persisted session through the CLI's own ``/compact`` turn.

        A slash command is the CLI's vocabulary rather than the event protocol's,
        so it stays in the backend that also owns the ``resume`` option it needs.
        """
        response = await self.reply("/compact", resume=session_id)
        if not response.success:
            raise RuntimeError(f"Session compaction failed: {response.answer}")

    async def _start(self) -> None:
        from claude_agent_sdk import __version__

        self.cwd.mkdir(parents=True, exist_ok=True)
        if config_dir := self.config_dir:
            config_dir.mkdir(parents=True, exist_ok=True)
        self._job_tool_server = JobToolServer.resolve(self.job_tools, self.app_context)
        self.logger.info(
            f"Agent backend ready: name={self.name} package={self.SDK_PACKAGE} version={__version__}"
        )

    def _build_options(self, overrides: dict) -> ClaudeAgentOptions:
        """Merge component defaults with call-time options into one SDK options object."""
        from claude_agent_sdk import ClaudeAgentOptions

        depth = overrides.get(AGENT_DEPTH_ARGUMENT, 0)
        if isinstance(depth, bool) or not isinstance(depth, int) or depth < 0:
            raise ValueError(f"{AGENT_DEPTH_ARGUMENT} must be a non-negative integer")
        call_options = self._known_options(
            overrides, reserved=frozenset({AGENT_DEPTH_ARGUMENT})
        )
        options = {**self.options, **call_options}
        options["cwd"] = str(self._resolve_cwd(options.get("cwd")))
        # Only the workspace's own .claude/ is honoured: the operator's personal
        # settings would otherwise silently change how a server-side agent runs.
        options.setdefault("setting_sources", ["project"])
        env = {
            **self.subprocess_environment,
            **(self.options.get("env") or {}),
            **(call_options.get("env") or {}),
        }
        if config_dir := self.config_dir:
            env.setdefault("CLAUDE_CONFIG_DIR", str(config_dir))
        options["env"] = env
        if self._job_tool_server is not None:
            self._job_tool_server.attach(options, depth)
        return ClaudeAgentOptions(**options)

    async def reply_stream(self, prompt: str, **options) -> AsyncIterator[JobEvent]:
        """Stream one agent turn as AxonX events.

        Every message the CLI emits rides out inside a ``BackendEvent`` envelope,
        carrying its own class name and payload verbatim, and the terminal result
        message becomes the stream's single ``ResultEvent``.
        """
        from claude_agent_sdk import ResultMessage, query

        opts = self._build_options(options)
        self.logger.info(
            f"Agent turn: name={self.name} model={opts.model} cwd={opts.cwd} "
            f"resume={opts.resume or '-'} skills={opts.skills or '-'}",
        )
        async with aclosing(query(prompt=prompt, options=opts)) as stream:
            async for message in stream:
                if isinstance(message, ResultMessage):
                    yield ResultEvent.from_response(_to_response(message))
                    # The SDK may emit housekeeping frames, or surface its CLI's
                    # non-zero exit, after an error result. The result is AxonX's
                    # terminal event, so close the SDK stream at this boundary.
                    return
                yield BackendEvent(
                    type_name=type(message).__name__, message=_message_payload(message)
                )
        # A stream without its terminal event would leave every consumer to
        # invent an outcome; failing here names the backend as the culprit.
        raise RuntimeError(f"{type(self).__name__} produced no result message")
