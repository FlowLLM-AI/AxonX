"""Claude Code backend implemented with the interactive Agent SDK client."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import suppress
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from ..base import BaseAgentComponent
from .projector import (
    ClaudeMessageProjector,
    history_blocks,
)
from .session_store import ClaudeSessionStoreAdapter
from .tools import JobToolServer
from ..events import AgentMessageEvent
from ..local_session_store import LocalAgentSessionStore
from ..models import AgentSession, AgentSessionInfo
from ...job.events import JobEvent, ResultEvent
from ...job.models import JobResponse
from .....common.registry import provider

if TYPE_CHECKING:
    from claude_agent_sdk import (
        ClaudeAgentOptions,
        ClaudeSDKClient,
        ResultMessage,
        SystemPromptPreset,
    )


def _to_response(result: ResultMessage) -> JobResponse:
    payload = asdict(result)
    success = not result.is_error
    fallback = result.result or "; ".join(result.errors or ())
    answer = result.structured_output if success and result.structured_output is not None else fallback
    return JobResponse(answer=answer, success=success, metadata=payload)


@provider("claude")
class ClaudeAgentComponent(BaseAgentComponent):
    """Expose Claude Code sessions without inventing a second session identity."""

    SDK_PACKAGE = "claude-agent-sdk"

    def __init__(
        self,
        job_tools: Sequence[str] = (),
        state_dir: str = "agent/claude",
        session_store: Mapping[str, Any] | None = None,
        **kwargs,
    ) -> None:
        from claude_agent_sdk import ClaudeAgentOptions

        super().__init__(**kwargs)
        if isinstance(job_tools, str):
            raise TypeError("job_tools must be a sequence of Job names, not a string")
        self.options = dict(self.kwargs)
        ClaudeAgentOptions(**self.options)
        reserved = {"resume", "session_id", "continue_conversation", "session_store"}
        configured = sorted(reserved & self.options.keys())
        if configured:
            raise ValueError("Session lifecycle options are managed by AxonX: " + ", ".join(configured))
        self.job_tools = tuple(dict.fromkeys(job_tools))
        self.state_dir = state_dir
        store_config = dict(session_store or {})
        backend = store_config.pop("backend", "local")
        if backend != "local":
            raise ValueError(f"Unknown Agent session store backend: {backend!r}")
        store_path = store_config.pop("path", "agent/session-store")
        if store_config:
            raise ValueError("Unknown Agent session store options: " + ", ".join(sorted(store_config)))
        self._store_path = str(store_path)
        self._sdk_store: ClaudeSessionStoreAdapter | None = None
        self._job_tool_server: JobToolServer | None = None
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._active: dict[str, ClaudeSDKClient] = {}

    @property
    def cwd(self) -> Path:
        configured = self.options.get("cwd")
        if not configured:
            return self.workspace.root
        path = Path(configured).expanduser()
        return self.workspace.locate(path, external=path.is_absolute())

    @property
    def config_dir(self) -> Path | None:
        environment = {**self.subprocess_environment, **(self.options.get("env") or {})}
        if not self.state_dir or "CLAUDE_CONFIG_DIR" in environment:
            return None
        return self.workspace.locate(Path(self.state_dir) / self.name)

    @property
    def subprocess_environment(self) -> dict[str, str]:
        return dict(self.app_config.environment)

    @property
    def sdk_store(self) -> ClaudeSessionStoreAdapter:
        if self._sdk_store is None:
            raise RuntimeError("Agent session store is not started")
        return self._sdk_store

    async def _start(self) -> None:
        from claude_agent_sdk import __version__

        await super()._start()
        self.cwd.mkdir(parents=True, exist_ok=True)
        if config_dir := self.config_dir:
            config_dir.mkdir(parents=True, exist_ok=True)
        self._sdk_store = ClaudeSessionStoreAdapter(LocalAgentSessionStore(self.workspace.locate(self._store_path)))
        self._job_tool_server = JobToolServer.resolve(self.job_tools, self.app_context)
        self.logger.info(f"Agent backend ready: name={self.name} package={self.SDK_PACKAGE} " f"version={__version__}")

    async def _close(self) -> None:
        clients = tuple(self._active.values())
        if clients:
            await asyncio.gather(*(client.interrupt() for client in clients), return_exceptions=True)
            await asyncio.gather(*(client.disconnect() for client in clients), return_exceptions=True)
        self._active.clear()

    def _system_prompt_with_guide(self) -> str | SystemPromptPreset:
        prompt = self.options.get("system_prompt")
        if prompt is None:
            prompt = {"type": "preset", "preset": "claude_code"}
        if isinstance(prompt, dict) and prompt.get("type") == "file":
            path = Path(prompt["path"]).expanduser()
            if not path.is_absolute():
                path = self.cwd / path
            prompt = path.read_text(encoding="utf-8")
        if isinstance(prompt, str):
            return "\n\n".join(part for part in (prompt, self.dev_guide) if part)
        return {**prompt, "append": "\n\n".join(part for part in (prompt.get("append", ""), self.dev_guide) if part)}

    def _build_options(self, *, session_id: str, resume: bool, depth: int) -> ClaudeAgentOptions:
        from claude_agent_sdk import ClaudeAgentOptions

        options = dict(self.options)
        if self.dev_guide:
            options["system_prompt"] = self._system_prompt_with_guide()
        options["cwd"] = str(self.cwd)
        options.setdefault("setting_sources", ["project"])
        options["include_partial_messages"] = True
        options["session_store"] = self.sdk_store
        options["session_id" if not resume else "resume"] = session_id
        env = {**self.subprocess_environment, **(options.get("env") or {})}
        if config_dir := self.config_dir:
            env.setdefault("CLAUDE_CONFIG_DIR", str(config_dir))
        options["env"] = env
        if self._job_tool_server is not None:
            self._job_tool_server.attach(options, depth)
        return ClaudeAgentOptions(**options)

    async def _session_exists(self, session_id: str) -> bool:
        from claude_agent_sdk import project_key_for_directory

        entries = await self.sdk_store.load(
            {
                "project_key": project_key_for_directory(self.cwd),
                "session_id": session_id,
            }
        )
        return entries is not None

    # Async generators satisfy the base contract returning an AsyncIterator.
    async def reply_stream(  # pylint: disable=invalid-overridden-method
        self,
        message: str,
        *,
        session_id: str | None = None,
        depth: int = 0,
    ) -> AsyncIterator[JobEvent]:
        from claude_agent_sdk import ClaudeSDKClient, ResultMessage

        if not message.strip():
            raise ValueError("Agent message must not be empty")
        resume = session_id is not None
        current_session = session_id or str(uuid4())

        async with self._locks[current_session]:
            if resume:
                await self._require_session(current_session)
            options = self._build_options(session_id=current_session, resume=resume, depth=depth)
            client = ClaudeSDKClient(options)
            projector = ClaudeMessageProjector()
            sequence = 0
            result_seen = False
            try:
                await client.connect()
                self._active[current_session] = client
                yield AgentMessageEvent(
                    session_id=current_session,
                    type_name="SessionStart",
                    message_uuid=f"{current_session}:init",
                    role="system",
                    sequence=sequence,
                )
                sequence += 1
                await client.query(message, session_id=current_session)
                async for sdk_message in client.receive_response():
                    type_name = type(sdk_message).__name__
                    event_session = getattr(sdk_message, "session_id", None) or current_session
                    patches = projector.project(sdk_message)
                    if isinstance(sdk_message, ResultMessage):
                        patches.extend(
                            projector.finish_open(
                                cancelled=sdk_message.terminal_reason in {"aborted_streaming", "aborted_tools"}
                            )
                        )
                    yield AgentMessageEvent(
                        session_id=event_session,
                        type_name=type_name,
                        message_uuid=str(
                            getattr(sdk_message, "uuid", None)
                            or getattr(sdk_message, "message_id", None)
                            or f"{event_session}:{sequence}"
                        ),
                        role={"UserMessage": "user", "AssistantMessage": "assistant", "StreamEvent": "assistant"}.get(
                            type_name, "system"
                        ),
                        sequence=sequence,
                        presentation=patches,
                    )
                    sequence += 1
                    if isinstance(sdk_message, ResultMessage):
                        result_seen = True
                        yield ResultEvent.from_response(_to_response(sdk_message))
                        return
            finally:
                self._active.pop(current_session, None)
                if not result_seen:
                    with suppress(Exception):
                        await client.interrupt()
                await client.disconnect()
            if not result_seen:
                raise RuntimeError("Claude SDK produced no ResultMessage")

    async def list_sessions(self, *, limit: int | None = None, offset: int = 0) -> list[AgentSessionInfo]:
        from claude_agent_sdk import list_sessions_from_store

        sessions = await list_sessions_from_store(self.sdk_store, directory=str(self.cwd), limit=limit, offset=offset)
        return [AgentSessionInfo(**asdict(item), backend=self.backend) for item in sessions]

    async def get_session(self, session_id: str, *, limit: int | None = None, offset: int = 0) -> AgentSession:
        from claude_agent_sdk import (
            get_session_info_from_store,
            get_session_messages_from_store,
        )

        info = await get_session_info_from_store(self.sdk_store, session_id, directory=str(self.cwd))
        if info is None:
            raise KeyError(f"Agent session not found: {session_id}")
        messages = await get_session_messages_from_store(
            self.sdk_store,
            session_id,
            directory=str(self.cwd),
            limit=limit,
            offset=offset,
        )
        return AgentSession(
            info=AgentSessionInfo(**asdict(info), backend=self.backend),
            blocks=history_blocks(messages),
        )

    async def rename_session(self, session_id: str, title: str) -> None:
        from claude_agent_sdk import rename_session_via_store

        await self._require_session(session_id)
        await rename_session_via_store(self.sdk_store, session_id, title, directory=str(self.cwd))

    async def tag_session(self, session_id: str, tag: str | None) -> None:
        from claude_agent_sdk import tag_session_via_store

        await self._require_session(session_id)
        await tag_session_via_store(self.sdk_store, session_id, tag, directory=str(self.cwd))

    async def delete_session(self, session_id: str) -> None:
        from claude_agent_sdk import delete_session_via_store

        if self._locks[session_id].locked():
            raise RuntimeError("Cannot delete a running Agent session")
        async with self._locks[session_id]:
            await self._require_session(session_id)
            await delete_session_via_store(self.sdk_store, session_id, directory=str(self.cwd))

    async def fork_session(
        self,
        session_id: str,
        *,
        up_to_message_id: str | None = None,
        title: str | None = None,
    ) -> str:
        from claude_agent_sdk import fork_session_via_store

        result = await fork_session_via_store(
            self.sdk_store,
            session_id,
            directory=str(self.cwd),
            up_to_message_id=up_to_message_id,
            title=title,
        )
        return result.session_id

    async def cancel_turn(self, session_id: str) -> None:
        client = self._active.get(session_id)
        if client is None:
            raise KeyError(f"Agent session is not running: {session_id}")
        await client.interrupt()

    async def _require_session(self, session_id: str) -> None:
        if not await self._session_exists(session_id):
            raise KeyError(f"Agent session not found: {session_id}")
