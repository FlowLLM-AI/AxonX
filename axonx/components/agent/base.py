"""Backend-neutral Agent component contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from importlib.resources import files
from typing import Any

from ...enums import ComponentEnum
from ..base import BaseComponent
from ..job.contracts import JobResponse
from ..job.events import JobEvent, fold_events


class BaseAgentComponent(BaseComponent, ABC):
    """Own Agent sessions and expose them through AxonX Job events."""

    component_type = ComponentEnum.AGENT

    def __init__(self, load_dev_guide: bool = False, **kwargs) -> None:
        super().__init__(**kwargs)
        if not isinstance(load_dev_guide, bool):
            raise TypeError("load_dev_guide must be a boolean")
        self.load_dev_guide = load_dev_guide
        self.dev_guide = ""

    async def _start(self) -> None:
        await super()._start()
        self.dev_guide = ""
        if self.load_dev_guide:
            language = self.app_config.language if self.app_context is not None else "en"
            self.dev_guide = files(__package__).joinpath("guides", f"{language}.md").read_text(encoding="utf-8")

    @abstractmethod
    def reply_stream(
        self,
        message: str,
        *,
        session_id: str | None = None,
        depth: int = 0,
    ) -> AsyncIterator[JobEvent]:
        """Run one turn, creating a backend session when the ID is absent."""

    async def reply(self, message: str, *, session_id: str | None = None, depth: int = 0) -> JobResponse:
        return await fold_events(self.reply_stream(message, session_id=session_id, depth=depth))

    @abstractmethod
    async def list_sessions(self, *, limit: int | None = None, offset: int = 0) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def get_session(self, session_id: str, *, limit: int | None = None, offset: int = 0) -> dict[str, Any]: ...

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
