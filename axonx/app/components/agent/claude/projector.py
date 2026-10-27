"""Translate Claude messages, results and history into public Agent events and blocks."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
from typing import TYPE_CHECKING, Any, Literal

from .....client.events import AgentBlockPatch, AgentBlockType, AgentMessageEvent, ResultEvent
from ..models import AgentHistoryBlock

if TYPE_CHECKING:
    from claude_agent_sdk import SessionMessage


class ClaudeMessageProjector:
    """Own SDK-to-public conversion and reconcile partial and complete content."""

    def __init__(self) -> None:
        self._blocks: dict[str, AgentHistoryBlock] = {}
        self._indices: dict[int, str] = {}

    def events(self, message: Any, *, session_id: str, sequence: int) -> list[AgentMessageEvent | ResultEvent]:
        """Preserve one message event per SDK message, followed by its final result."""
        from claude_agent_sdk import ResultMessage

        session_id = getattr(message, "session_id", None) or session_id
        type_name = type(message).__name__
        patches = self.project(message)
        if isinstance(message, ResultMessage):
            patches.extend(
                self.finish_open(cancelled=message.terminal_reason in {"aborted_streaming", "aborted_tools"})
            )
        events: list[AgentMessageEvent | ResultEvent] = [
            AgentMessageEvent(
                session_id=session_id,
                type_name=type_name,
                message_uuid=str(
                    getattr(message, "uuid", None) or getattr(message, "message_id", None) or f"{session_id}:{sequence}"
                ),
                role={"UserMessage": "user", "AssistantMessage": "assistant", "StreamEvent": "assistant"}.get(
                    type_name, "system"
                ),
                sequence=sequence,
                presentation=patches,
            )
        ]
        if isinstance(message, ResultMessage):
            success = not message.is_error
            answer = message.result or "; ".join(message.errors or ())
            if success and message.structured_output is not None:
                answer = message.structured_output
            events.append(ResultEvent(answer=answer, success=success, metadata=asdict(message)))
        return events

    @staticmethod
    def _kind(block: Mapping[str, Any]) -> AgentBlockType | None:
        return {
            "text": "text",
            "thinking": "thinking",
            "tool_use": "tool",
            "server_tool_use": "tool",
        }.get(block.get("type"))

    def _patch(
        self,
        block_id: str,
        operation: Literal["start", "append", "replace", "finish"],
        *,
        delta: str = "",
        payload: dict[str, Any] | None = None,
    ) -> AgentBlockPatch:
        patch = AgentBlockPatch(
            operation=operation,
            block_id=block_id,
            block_type=self._blocks[block_id].block_type,
            delta=delta,
            payload=payload or {},
        )
        block = self._blocks[block_id]
        details = dict(patch.payload)
        text = details.pop("text", None)
        status = details.pop("status", None)
        if operation == "append":
            block.text += delta
        elif operation == "replace" and isinstance(text, str):
            block.text = text
        if isinstance(status, str):
            block.status = status
        elif operation == "finish":
            block.status = "completed"
        block.payload.update(details)
        return patch

    def _start(
        self,
        block_id: str,
        kind: AgentBlockType,
        message_uuid: str,
        *,
        role: Literal["user", "assistant", "system"] = "assistant",
        payload: dict[str, Any] | None = None,
    ) -> AgentBlockPatch:
        self._blocks[block_id] = AgentHistoryBlock(
            block_id=block_id,
            block_type=kind,
            message_uuid=message_uuid,
            role=role,
            status="running",
            text="",
        )
        return self._patch(block_id, "start", payload=payload)

    @staticmethod
    def _tool_input(raw: Mapping[str, Any]) -> dict[str, Any]:
        return {"name": raw.get("name"), "input": raw.get("input") or {}}

    def project(self, message: Any) -> list[AgentBlockPatch]:
        from claude_agent_sdk import AssistantMessage, StreamEvent, UserMessage

        if isinstance(message, StreamEvent):
            return self._stream(message.uuid, message.event)
        if isinstance(message, AssistantMessage):
            patches = self._content(
                message.uuid or message.message_id or "assistant",
                message.content,
            )
            self._indices.clear()
            return patches
        if isinstance(message, UserMessage) and isinstance(message.content, list):
            # The caller already displays the user's prompt; only tool results need replaying.
            return self._content(message.uuid or "user", message.content, role="user", results_only=True)
        return []

    def _stream(self, message_uuid: str, event: Mapping[str, Any]) -> list[AgentBlockPatch]:
        event_type = event.get("type")
        if event_type == "message_start":
            self._indices.clear()
        index = event.get("index")
        if not isinstance(index, int):
            return []
        if event_type == "content_block_start":
            return self._stream_start(message_uuid, index, event["content_block"])
        block_id = self._indices.get(index)
        if block_id is None:
            return []
        if event_type == "content_block_delta":
            return self._stream_delta(block_id, event["delta"])
        if event_type == "content_block_stop":
            tool = self._blocks[block_id].block_type == "tool"
            return [
                self._patch(block_id, "replace" if tool else "finish", payload={"status": "running"} if tool else None)
            ]
        return []

    def _stream_start(self, message_uuid: str, index: int, raw: Mapping[str, Any]) -> list[AgentBlockPatch]:
        kind = self._kind(raw)
        if kind is None:
            return []
        block_id = str(raw.get("id") or f"{message_uuid}:{index}") if kind == "tool" else f"{message_uuid}:{index}"
        self._indices[index] = block_id
        payload = {**self._tool_input(raw), "status": "building_input"} if kind == "tool" else None
        patches = [self._start(block_id, kind, message_uuid, payload=payload)]
        text = raw.get(kind, "") if kind != "tool" else ""
        if text:
            patches.append(self._patch(block_id, "append", delta=text))
        return patches

    def _stream_delta(self, block_id: str, delta: Mapping[str, Any]) -> list[AgentBlockPatch]:
        field = {"text_delta": "text", "thinking_delta": "thinking", "input_json_delta": "partial_json"}.get(
            delta.get("type")
        )
        if field is None:
            return []
        text = str(delta.get(field) or "")
        return [self._patch(block_id, "append", delta=text)]

    def _content(
        self,
        message_uuid: str,
        content: list[Any],
        *,
        role: Literal["user", "assistant", "system"] = "assistant",
        results_only: bool = False,
    ) -> list[AgentBlockPatch]:
        patches: list[AgentBlockPatch] = []
        for index, raw in enumerate(content):
            if not isinstance(raw, Mapping):
                kind = {
                    "TextBlock": "text",
                    "ThinkingBlock": "thinking",
                    "ToolUseBlock": "tool_use",
                    "ServerToolUseBlock": "server_tool_use",
                    "ToolResultBlock": "tool_result",
                    "ServerToolResultBlock": "server_tool_result",
                }.get(type(raw).__name__)
                if kind is None:
                    continue
                raw = {"type": kind, **asdict(raw)}
            if raw.get("type") in {"tool_result", "server_tool_result"}:
                block_id = str(raw.get("tool_use_id"))
                if block_id not in self._blocks:
                    patches.append(self._start(block_id, "tool", message_uuid, role=role))
                is_error = bool(raw.get("is_error"))
                patches.append(
                    self._patch(
                        block_id,
                        "finish",
                        payload={
                            "result": raw.get("content"),
                            "status": "failed" if is_error else "succeeded",
                        },
                    )
                )
                continue
            kind = self._kind(raw)
            if results_only or kind is None:
                continue
            block_id = (
                str(raw.get("id") or f"{message_uuid}:{index}")
                if kind == "tool"
                else (self._indices.get(index) or f"{message_uuid}:{index}")
            )
            payload = self._tool_input(raw) if kind == "tool" else None
            if block_id not in self._blocks:
                patches.append(self._start(block_id, kind, message_uuid, role=role, payload=payload))
            elif kind == "tool":
                patches.append(self._patch(block_id, "replace", payload={**payload, "text": "", "status": "running"}))
            if kind != "tool":
                block = self._blocks[block_id]
                text = raw.get(kind) or ""
                if text != block.text:
                    patches.append(self._patch(block_id, "replace", payload={"text": text}))
                if block.status == "running":
                    patches.append(self._patch(block_id, "finish"))
        return patches

    def finish_open(self, *, cancelled: bool = False) -> list[AgentBlockPatch]:
        return [
            self._patch(block_id, "finish", payload={"status": "cancelled" if cancelled else "completed"})
            for block_id, block in self._blocks.items()
            if block.status in {"running", "building_input"}
        ]

    @classmethod
    def history(cls, messages: list[SessionMessage]) -> list[AgentHistoryBlock]:
        """Fold persisted messages using the same content and tool-result semantics."""
        projector = cls()
        for item in messages:
            if not isinstance(item.message, Mapping):
                continue
            content = item.message.get("content")
            if isinstance(content, str):
                content = [{"type": "text", "text": content}]
            if isinstance(content, list):
                projector._content(item.uuid, content, role=item.type)
        return list(projector._blocks.values())
