"""Run one interactive Agent session turn as a streaming Job Step."""

from contextlib import aclosing
from typing import ClassVar

from ...components.job.events import ResultEvent
from ...components.registry import provider
from ...constants import AGENT_DEPTH_ARGUMENT
from ...enums import ComponentEnum
from ..base import BaseStep


@provider("agent_stream")
class AgentStreamStep(BaseStep):
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

    async def execute(self):
        if self.depth >= self.max_depth:
            self._refuse_depth()
            return

        result_seen = False
        stream_source = self.agent_wrapper.reply_stream(
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
                        raise RuntimeError(
                            "Agent backend produced an event after its result"
                        )
                    await self.emit(event)
        if not result_seen:
            raise RuntimeError("Agent backend produced no result")
