"""Claude Code backend implemented with the interactive Agent SDK client."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from collections import defaultdict
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import asdict, fields
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from ....constants import AGENT_DEPTH_ARGUMENT
from ...job.contracts import JobResponse
from ...job.events import AgentMessageEvent, JobEvent, ResultEvent
from ...registry import provider
from ..base import BaseAgentComponent
from ..local_session_store import LocalAgentSessionStore
from .projector import ClaudeMessageProjector, history_blocks, message_payload
from .session_store import ClaudeSessionStoreAdapter
from .tools import JobToolServer

if TYPE_CHECKING:
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, ResultMessage


@lru_cache(maxsize=1)
def _option_names() -> frozenset[str]:
    from claude_agent_sdk import ClaudeAgentOptions

    return frozenset(field.name for field in fields(ClaudeAgentOptions))


def _to_response(result: ResultMessage) -> JobResponse:
    payload = asdict(result)
    success = not result.is_error
    fallback = result.result or "; ".join(result.errors or ())
    answer = (
        result.structured_output
        if success and result.structured_output is not None
        else fallback
    )
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
        super().__init__(**kwargs)
        if isinstance(job_tools, str):
            raise TypeError("job_tools must be a sequence of Job names, not a string")
        self.options = {
            name: value for name, value in self.kwargs.items() if name in _option_names()
        }
        unknown = sorted(set(self.kwargs) - _option_names())
        if unknown:
            raise ValueError(f"Unknown Claude agent options: {', '.join(unknown)}")
        reserved = {"resume", "session_id", "continue_conversation", "session_store"}
        configured = sorted(reserved & self.options.keys())
        if configured:
            raise ValueError(
                "Session lifecycle options are managed by AxonX: "
                + ", ".join(configured)
            )
        self.job_tools = tuple(job_tools)
        self.state_dir = state_dir
        store_config = dict(session_store or {})
        backend = store_config.pop("backend", "local")
        if backend != "local":
            raise ValueError(f"Unknown Agent session store backend: {backend!r}")
        store_path = store_config.pop("path", "agent/session-store")
        if store_config:
            raise ValueError(
                "Unknown Agent session store options: "
                + ", ".join(sorted(store_config))
            )
        self._store_path = str(store_path)
        self._store: LocalAgentSessionStore | None = None
        self._sdk_store: ClaudeSessionStoreAdapter | None = None
        self._job_tool_server: JobToolServer | None = None
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._active: dict[str, ClaudeSDKClient] = {}

    def _inside_workspace(self, value: str) -> Path:
        workspace = self.workspace_path.resolve(strict=False)
        path = Path(value).expanduser()
        resolved = (
            path.resolve(strict=False)
            if path.is_absolute()
            else (workspace / path).resolve(strict=False)
        )
        if not resolved.is_relative_to(workspace):
            raise ValueError("Agent state paths must resolve inside the workspace")
        return resolved

    @property
    def cwd(self) -> Path:
        configured = self.options.get("cwd")
        if not configured:
            return self.workspace_path.resolve(strict=False)
        path = Path(configured).expanduser()
        return path.resolve(strict=False) if path.is_absolute() else self._inside_workspace(str(path))

    @property
    def config_dir(self) -> Path | None:
        environment = {**self.subprocess_environment, **(self.options.get("env") or {})}
        if not self.state_dir or "CLAUDE_CONFIG_DIR" in environment:
            return None
        return self._inside_workspace(self.state_dir) / self.name

    @property
    def subprocess_environment(self) -> dict[str, str]:
        return dict(self.app_config.environment) if self.app_context is not None else {}

    @property
    def sdk_store(self) -> ClaudeSessionStoreAdapter:
        if self._sdk_store is None:
            raise RuntimeError("Agent session store is not started")
        return self._sdk_store

    async def _start(self) -> None:
        from claude_agent_sdk import __version__

        self.cwd.mkdir(parents=True, exist_ok=True)
        if config_dir := self.config_dir:
            config_dir.mkdir(parents=True, exist_ok=True)
        self._store = LocalAgentSessionStore(self._inside_workspace(self._store_path))
        self._sdk_store = ClaudeSessionStoreAdapter(self._store)
        self._job_tool_server = JobToolServer.resolve(self.job_tools, self.app_context)
        self.logger.info(
            f"Agent backend ready: name={self.name} package={self.SDK_PACKAGE} "
            f"version={__version__}"
        )

    async def _close(self) -> None:
        clients = tuple(self._active.values())
        if clients:
            await asyncio.gather(
                *(client.interrupt() for client in clients), return_exceptions=True
            )
            await asyncio.gather(
                *(client.disconnect() for client in clients), return_exceptions=True
            )
        self._active.clear()

    def _build_options(
        self, *, session_id: str, resume: bool, depth: int
    ) -> ClaudeAgentOptions:
        from claude_agent_sdk import ClaudeAgentOptions

        if isinstance(depth, bool) or not isinstance(depth, int) or depth < 0:
            raise ValueError(f"{AGENT_DEPTH_ARGUMENT} must be a non-negative integer")
        options = dict(self.options)
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

    async def reply_stream(
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
            if resume and not await self._session_exists(current_session):
                raise KeyError(f"Agent session not found: {current_session}")
            options = self._build_options(
                session_id=current_session, resume=resume, depth=depth
            )
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
                    message={"session_id": current_session, "resumed": resume},
                    sequence=sequence,
                )
                sequence += 1
                await client.query(message, session_id=current_session)
                async for sdk_message in client.receive_response():
                    event_session = getattr(sdk_message, "session_id", None) or current_session
                    patches = projector.project(sdk_message)
                    if isinstance(sdk_message, ResultMessage):
                        patches.extend(
                            projector.finish_open(
                                cancelled=sdk_message.terminal_reason
                                in {"aborted_streaming", "aborted_tools"}
                            )
                        )
                    yield AgentMessageEvent(
                        session_id=event_session,
                        type_name=type(sdk_message).__name__,
                        message=message_payload(sdk_message),
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

    async def list_sessions(
        self, *, limit: int | None = None, offset: int = 0
    ) -> list[dict[str, Any]]:
        from claude_agent_sdk import list_sessions_from_store

        sessions = await list_sessions_from_store(
            self.sdk_store, directory=str(self.cwd), limit=limit, offset=offset
        )
        return [{**asdict(item), "backend": self.backend} for item in sessions]

    async def get_session(
        self, session_id: str, *, limit: int | None = None, offset: int = 0
    ) -> dict[str, Any]:
        from claude_agent_sdk import (
            get_session_info_from_store,
            get_session_messages_from_store,
        )

        info = await get_session_info_from_store(
            self.sdk_store, session_id, directory=str(self.cwd)
        )
        if info is None:
            raise KeyError(f"Agent session not found: {session_id}")
        messages = await get_session_messages_from_store(
            self.sdk_store,
            session_id,
            directory=str(self.cwd),
            limit=limit,
            offset=offset,
        )
        return {
            "info": {**asdict(info), "backend": self.backend},
            "messages": [asdict(item) for item in messages],
            "blocks": history_blocks(messages),
        }

    async def rename_session(self, session_id: str, title: str) -> None:
        from claude_agent_sdk import rename_session_via_store

        if not await self._session_exists(session_id):
            raise KeyError(f"Agent session not found: {session_id}")
        await rename_session_via_store(
            self.sdk_store, session_id, title, directory=str(self.cwd)
        )

    async def tag_session(self, session_id: str, tag: str | None) -> None:
        from claude_agent_sdk import tag_session_via_store

        if not await self._session_exists(session_id):
            raise KeyError(f"Agent session not found: {session_id}")
        await tag_session_via_store(
            self.sdk_store, session_id, tag, directory=str(self.cwd)
        )

    async def delete_session(self, session_id: str) -> None:
        from claude_agent_sdk import delete_session_via_store

        if session_id in self._active:
            raise RuntimeError("Cannot delete a running Agent session")
        if not await self._session_exists(session_id):
            raise KeyError(f"Agent session not found: {session_id}")
        await delete_session_via_store(
            self.sdk_store, session_id, directory=str(self.cwd)
        )

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

    async def compact_session(self, session_id: str) -> None:
        response = await self.reply("/compact", session_id=session_id)
        if not response.success:
            raise RuntimeError(f"Session compaction failed: {response.answer}")
