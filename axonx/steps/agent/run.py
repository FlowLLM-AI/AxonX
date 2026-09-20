"""Run one agent turn and adapt its event stream to a Job Step."""

from contextlib import aclosing
from typing import ClassVar

from ...components.job.base import JobResponse, ResultEvent
from ...components.registry import provider
from ...constants import AGENT_DEPTH_ARGUMENT
from ...enums import ComponentEnum
from ..base import BaseStep


class BaseAgentStep(BaseStep):
    """Drive one agent backend while bounding recursive Job tool calls."""

    component_domains = (ComponentEnum.AGENT,)
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
        self.response.answer = (
            f"Agent call chain is limited to {self.max_depth} nested turns."
        )
        self.response.metadata = {
            AGENT_DEPTH_ARGUMENT: self.depth,
            "session_id": self.context.get("session_id"),
        }

    def _adopt(self, response: JobResponse) -> None:
        self.response.answer = response.answer
        self.response.success = response.success
        self.response.metadata = dict(response.metadata)

    async def run_turn(self, *, partial: bool) -> None:
        if self.depth >= self.max_depth:
            self._refuse_depth()
            return

        options = {AGENT_DEPTH_ARGUMENT: self.depth}
        if partial:
            options["include_partial_messages"] = True
        if session_id := self.context.get("session_id"):
            options["resume"] = session_id

        result_seen = False
        stream_source = self.agent_wrapper.reply_stream(
            self.context["prompt"], **options
        )
        async with aclosing(stream_source) as stream:
            async for event in stream:
                if isinstance(event, ResultEvent):
                    if result_seen:
                        raise RuntimeError("Agent backend produced multiple results")
                    result_seen = True
                    self._adopt(event)
                else:
                    if result_seen:
                        raise RuntimeError(
                            "Agent backend produced an event after its result"
                        )
                    await self.emit(event)
        if not result_seen:
            raise RuntimeError("Agent backend produced no result")


@provider("agent_stream")
class AgentStreamStep(BaseAgentStep):
    """Publish incremental backend events and fold the terminal result."""

    async def execute(self):
        await self.run_turn(partial=True)


@provider("agent")
class AgentStep(BaseAgentStep):
    """Publish complete backend messages and fold the terminal result."""

    async def execute(self):
        await self.run_turn(partial=False)
