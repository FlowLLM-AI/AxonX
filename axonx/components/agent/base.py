"""Backend-neutral Agent component contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from ...enums import ComponentEnum
from ..base import BaseComponent
from ..job.contracts import JobResponse
from ..job.events import JobEvent, fold_events


class BaseAgentComponent(BaseComponent, ABC):
    """Own Agent sessions and expose them through AxonX Job events."""

    component_type = ComponentEnum.AGENT

    @abstractmethod
    def reply_stream(
        self,
        message: str,
        *,
        session_id: str | None = None,
        depth: int = 0,
    ) -> AsyncIterator[JobEvent]:
        """Run one turn, creating a backend session when the ID is absent."""

    async def reply(
        self, message: str, *, session_id: str | None = None, depth: int = 0
    ) -> JobResponse:
        return await fold_events(
            self.reply_stream(message, session_id=session_id, depth=depth)
        )

    @abstractmethod
    async def list_sessions(
        self, *, limit: int | None = None, offset: int = 0
    ) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def get_session(
        self, session_id: str, *, limit: int | None = None, offset: int = 0
    ) -> dict[str, Any]: ...

    @abstractmethod
    async def rename_session(self, session_id: str, title: str) -> None: ...

    @abstractmethod
    async def tag_session(self, session_id: str, tag: str | None) -> None: ...

    @abstractmethod
    async def delete_session(self, session_id: str) -> None: ...

    @abstractmethod
    async def fork_session(
        self,
        session_id: str,
        *,
        up_to_message_id: str | None = None,
        title: str | None = None,
    ) -> str: ...

    @abstractmethod
    async def cancel_turn(self, session_id: str) -> None: ...
