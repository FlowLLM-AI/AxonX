"""Job adapters for Agent turns and session management."""

from __future__ import annotations

from abc import ABC
from contextlib import aclosing
from typing import ClassVar

from ...client.events import ResultEvent
from ..components.agent.base import BaseAgentComponent
from ..components.agent.models import AGENT_DEPTH_ARGUMENT, AgentMutationResult
from ..components.registry import provider
from .base import BaseStep


@provider("agent_stream")
class AgentStreamStep(BaseStep):
    injected_parameters: ClassVar = {
        AGENT_DEPTH_ARGUMENT: {
            "type": "integer",
            "minimum": 0,
            "default": 0,
            "description": "Internal agent call-chain depth.",
        },
    }

    def __init__(self, max_depth: int = 3, **kwargs) -> None:
        super().__init__(**kwargs)
        if isinstance(max_depth, bool) or not isinstance(max_depth, int):
            raise TypeError("Agent max_depth must be an integer")
        if max_depth < 0:
            raise ValueError("Agent max_depth must be non-negative")
        self.max_depth = max_depth

    @property
    def depth(self) -> int:
        return self.context.get(AGENT_DEPTH_ARGUMENT, 0)

    def _refuse_depth(self) -> None:
        self.logger.warning(f"Agent call chain reached max_depth={self.max_depth}")
        self.response.success = False
        self.response.answer = f"Agent call chain is limited to {self.max_depth} nested turns."
        self.response.metadata = {
            AGENT_DEPTH_ARGUMENT: self.depth,
            "session_id": self.context.get("session_id"),
        }

    async def execute(self):
        if self.depth >= self.max_depth:
            self._refuse_depth()
            return

        result_seen = False
        stream_source = self.component(BaseAgentComponent).reply_stream(
            self.context["message"],
            session_id=self.context.get("session_id"),
            depth=self.depth,
        )
        async with aclosing(stream_source) as stream:
            async for event in stream:
                if isinstance(event, ResultEvent):
                    if result_seen:
                        raise RuntimeError("Agent backend produced multiple results")
                    result_seen = True
                    response = event.response()
                    self.response.answer = response.answer
                    self.response.success = response.success
                    self.response.metadata = dict(response.metadata)
                else:
                    if result_seen:
                        raise RuntimeError("Agent backend produced an event after its result")
                    await self.emit(event)
        if not result_seen:
            raise RuntimeError("Agent backend produced no result")


class AgentSessionStep(BaseStep, ABC):

    @property
    def agent(self) -> BaseAgentComponent:
        return self.component(BaseAgentComponent)


@provider("list_agent_sessions_step")
class ListAgentSessionsStep(AgentSessionStep):
    async def execute(self):
        self.response.answer = await self.agent.list_sessions(
            limit=self.context.get("limit"), offset=self.context.get("offset", 0)
        )


@provider("get_agent_session_step")
class GetAgentSessionStep(AgentSessionStep):
    async def execute(self):
        self.response.answer = await self.agent.get_session(
            self.context["session_id"],
            limit=self.context.get("limit"),
            offset=self.context.get("offset", 0),
        )


@provider("rename_agent_session_step")
class RenameAgentSessionStep(AgentSessionStep):
    async def execute(self):
        await self.agent.rename_session(self.context["session_id"], self.context["title"])
        self.response.answer = AgentMutationResult(session_id=self.context["session_id"])


@provider("tag_agent_session_step")
class TagAgentSessionStep(AgentSessionStep):
    async def execute(self):
        await self.agent.tag_session(self.context["session_id"], self.context.get("tag"))
        self.response.answer = AgentMutationResult(session_id=self.context["session_id"])


@provider("delete_agent_session_step")
class DeleteAgentSessionStep(AgentSessionStep):
    async def execute(self):
        await self.agent.delete_session(self.context["session_id"])
        self.response.answer = AgentMutationResult(session_id=self.context["session_id"])


@provider("fork_agent_session_step")
class ForkAgentSessionStep(AgentSessionStep):
    async def execute(self):
        session_id = await self.agent.fork_session(
            self.context["session_id"],
            up_to_message_id=self.context.get("up_to_message_id"),
            title=self.context.get("title"),
        )
        self.response.answer = AgentMutationResult(session_id=session_id)


@provider("cancel_agent_turn_step")
class CancelAgentTurnStep(AgentSessionStep):
    async def execute(self):
        await self.agent.cancel_turn(self.context["session_id"])
        self.response.answer = AgentMutationResult(session_id=self.context["session_id"])
