"""Agent component contract, expressed in AxonX event terms."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from ...enums import ComponentEnum
from ..job.base import JobEvent, JobResponse, fold_events
from ..base import BaseComponent


class BaseAgentComponent(BaseComponent, ABC):
    """Run one agent turn and hand back AxonX events.

    The protocol is AxonX's own ``JobEvent`` union, not the backend's message
    vocabulary: each backend message rides inside a ``BackendEvent`` envelope that
    keeps its payload verbatim, and the turn ends with the stream's single
    ``ResultEvent``. Callers read ``kind`` and never import the backend's SDK, while
    the backend's own fields survive untouched — an envelope to pass through, not
    a vocabulary to translate into.

    Streaming and non-streaming are two ways of consuming the same stream, not
    two implementations: :meth:`reply` folds it, :meth:`reply_stream` yields it.
    Nothing here names a backend: what a turn *is*, and whatever commands a
    particular CLI adds on top of it, belong to the backend owning that
    vocabulary.
    """

    component_type = ComponentEnum.AGENT

    @abstractmethod
    def reply_stream(self, prompt: str, **options) -> AsyncIterator[JobEvent]:
        """Yield this turn's events in arrival order, terminal ``ResultEvent`` last."""

    async def reply(self, prompt: str, **options) -> JobResponse:
        """Drain :meth:`reply_stream` and return its terminal response."""
        return await fold_events(self.reply_stream(prompt, **options))
