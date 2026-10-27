"""Agent Session query and mutation Steps."""

from __future__ import annotations

from abc import ABC

from ...components.agent.base import BaseAgentComponent
from ...components.agent.models import AgentMutationResult
from ...components.models import ComponentType
from ...components.registry import provider
from ..base import BaseStep


class AgentSessionStep(BaseStep, ABC):
    component_domains = (ComponentType.AGENT,)

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
