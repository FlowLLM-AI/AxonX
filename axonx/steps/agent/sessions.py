"""Agent Session query and mutation Steps."""

from __future__ import annotations

from ...components.registry import provider
from ...enums import ComponentEnum
from ..base import BaseStep


class AgentSessionStep(BaseStep):
    component_domains = (ComponentEnum.AGENT,)


@provider("list_agent_sessions_step")
class ListAgentSessionsStep(AgentSessionStep):
    async def execute(self):
        self.response.answer = await self.agent_wrapper.list_sessions(
            limit=self.context.get("limit"), offset=self.context.get("offset", 0)
        )


@provider("get_agent_session_step")
class GetAgentSessionStep(AgentSessionStep):
    async def execute(self):
        self.response.answer = await self.agent_wrapper.get_session(
            self.context["session_id"],
            limit=self.context.get("limit"),
            offset=self.context.get("offset", 0),
        )


@provider("rename_agent_session_step")
class RenameAgentSessionStep(AgentSessionStep):
    async def execute(self):
        await self.agent_wrapper.rename_session(
            self.context["session_id"], self.context["title"]
        )
        self.response.answer = {"session_id": self.context["session_id"]}


@provider("tag_agent_session_step")
class TagAgentSessionStep(AgentSessionStep):
    async def execute(self):
        await self.agent_wrapper.tag_session(
            self.context["session_id"], self.context.get("tag")
        )
        self.response.answer = {"session_id": self.context["session_id"]}


@provider("delete_agent_session_step")
class DeleteAgentSessionStep(AgentSessionStep):
    async def execute(self):
        await self.agent_wrapper.delete_session(self.context["session_id"])
        self.response.answer = {"session_id": self.context["session_id"]}


@provider("fork_agent_session_step")
class ForkAgentSessionStep(AgentSessionStep):
    async def execute(self):
        session_id = await self.agent_wrapper.fork_session(
            self.context["session_id"],
            up_to_message_id=self.context.get("up_to_message_id"),
            title=self.context.get("title"),
        )
        self.response.answer = {"session_id": session_id}


@provider("cancel_agent_turn_step")
class CancelAgentTurnStep(AgentSessionStep):
    async def execute(self):
        await self.agent_wrapper.cancel_turn(self.context["session_id"])
        self.response.answer = {"session_id": self.context["session_id"]}
