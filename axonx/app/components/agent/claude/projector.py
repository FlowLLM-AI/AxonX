"""Project Claude SDK messages into stable, UI-oriented block patches."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping

from ...job.events import AgentBlockPatch


if TYPE_CHECKING:
    from claude_agent_sdk import ContentBlock, SessionMessage


class ClaudeMessageProjector:
    """Stateful projection for one streamed Claude turn."""

    def __init__(self) -> None:
        self._blocks: dict[str, dict[str, Any]] = {}
        self._indices: dict[int, str] = {}

    @staticmethod
    def _kind(block: Mapping[str, Any]) -> str | None:
        return {
            "text": "text",
            "thinking": "thinking",
            "tool_use": "tool",
            "server_tool_use": "tool",
        }.get(block.get("type"))

    @staticmethod
    def _content(block: Mapping[str, Any], kind: str) -> str:
        if kind == "text":
            return str(block.get("text") or "")
        if kind == "thinking":
            return str(block.get("thinking") or "")
        return ""

    def _start(self, block_id: str, kind: str, *, payload: dict[str, Any] | None = None) -> AgentBlockPatch:
        self._blocks[block_id] = {"kind": kind, "text": "", "finished": False}
        return AgentBlockPatch(operation="start", block_id=block_id, block_type=kind, payload=payload or {})

    def project(self, message: Any) -> list[AgentBlockPatch]:
        from claude_agent_sdk import AssistantMessage, StreamEvent, UserMessage

        if isinstance(message, StreamEvent):
            return self._stream(message.uuid, message.event)
        if isinstance(message, AssistantMessage):
            patches = self._assistant(message.uuid or message.message_id or "assistant", message.content)
            self._indices.clear()
            return patches
        if isinstance(message, UserMessage) and isinstance(message.content, list):
            return self._tool_results(message.content)
        return []

    def _stream(self, message_uuid: str, event: Mapping[str, Any]) -> list[AgentBlockPatch]:
        event_type = event.get("type")
        if event_type == "message_start":
            self._indices.clear()
        index = event.get("index")
        if not isinstance(index, int):
            return []
        if event_type == "content_block_start":
            return self._stream_start(message_uuid, index, event)
        block_id = self._indices.get(index)
        if block_id is None:
            return []
        if event_type == "content_block_delta":
            return self._stream_delta(block_id, event)
        if event_type == "content_block_stop":
            return self._stream_stop(block_id)
        return []

    def _stream_start(self, message_uuid: str, index: int, event: Mapping[str, Any]) -> list[AgentBlockPatch]:
        block = event.get("content_block")
        if not isinstance(block, Mapping):
            return []
        kind = self._kind(block)
        if kind is None:
            return []
        tool_id = block.get("id") if kind == "tool" else None
        block_id = str(tool_id or f"{message_uuid}:{index}")
        self._indices[index] = block_id
        payload = (
            {
                "tool_use_id": tool_id,
                "name": block.get("name"),
                "input": block.get("input") or {},
                "input_text": "",
                "result": None,
                "is_error": False,
                "status": "building_input",
            }
            if kind == "tool"
            else {}
        )
        patches = [self._start(block_id, kind, payload=payload)]
        text = self._content(block, kind)
        if text:
            self._blocks[block_id]["text"] = text
            patches.append(AgentBlockPatch(operation="append", block_id=block_id, block_type=kind, delta=text))
        return patches

    def _stream_delta(self, block_id: str, event: Mapping[str, Any]) -> list[AgentBlockPatch]:
        state = self._blocks[block_id]
        delta = event.get("delta")
        if not isinstance(delta, Mapping):
            return []
        delta_type = delta.get("type")
        text = ""
        payload: dict[str, Any] = {}
        if delta_type == "text_delta":
            text = str(delta.get("text") or "")
        elif delta_type == "thinking_delta":
            text = str(delta.get("thinking") or "")
        elif delta_type == "input_json_delta":
            text = str(delta.get("partial_json") or "")
            payload = {"input_text_delta": text}
        else:
            return []
        state["text"] += text
        return [
            AgentBlockPatch(
                operation="append",
                block_id=block_id,
                block_type=state["kind"],
                delta=text,
                payload=payload,
            )
        ]

    def _stream_stop(self, block_id: str) -> list[AgentBlockPatch]:
        state = self._blocks[block_id]
        if state["kind"] == "tool":
            return [
                AgentBlockPatch(
                    operation="replace",
                    block_id=block_id,
                    block_type="tool",
                    payload={"status": "running"},
                )
            ]
        state["finished"] = True
        return [AgentBlockPatch(operation="finish", block_id=block_id, block_type=state["kind"])]

    def _assistant(self, message_uuid: str, content: list[ContentBlock]) -> list[AgentBlockPatch]:
        from claude_agent_sdk import (
            ServerToolResultBlock,
            ServerToolUseBlock,
            TextBlock,
            ThinkingBlock,
            ToolResultBlock,
            ToolUseBlock,
        )

        patches: list[AgentBlockPatch] = []
        for index, block in enumerate(content):
            if isinstance(block, (ToolResultBlock, ServerToolResultBlock)):
                patches.extend(self._tool_results([block]))
                continue
            if isinstance(block, (ToolUseBlock, ServerToolUseBlock)):
                kind, complete = "tool", ""
                block_id = block.id
                payload = {"tool_use_id": block.id, "name": block.name, "input": block.input, "status": "running"}
            elif isinstance(block, (TextBlock, ThinkingBlock)):
                kind = "text" if isinstance(block, TextBlock) else "thinking"
                complete = block.text if isinstance(block, TextBlock) else block.thinking
                block_id = self._indices.get(index) or f"{message_uuid}:{index}"
                payload = {}
            else:
                continue
            if block_id not in self._blocks:
                patches.append(self._start(block_id, kind, payload=payload))
            elif kind == "tool":
                patches.append(
                    AgentBlockPatch(
                        operation="replace",
                        block_id=block_id,
                        block_type="tool",
                        payload={"name": block.name, "input": block.input, "text": ""},
                    )
                )
            state = self._blocks[block_id]
            if kind == "tool":
                state["text"] = ""
            if kind in {"text", "thinking"} and complete != state["text"]:
                state["text"] = complete
                patches.append(
                    AgentBlockPatch(
                        operation="replace",
                        block_id=block_id,
                        block_type=kind,
                        payload={"text": complete},
                    )
                )
            if kind in {"text", "thinking"} and not state["finished"]:
                state["finished"] = True
                patches.append(AgentBlockPatch(operation="finish", block_id=block_id, block_type=kind))
        return patches

    def _tool_results(self, content: list[ContentBlock]) -> list[AgentBlockPatch]:
        from claude_agent_sdk import ServerToolResultBlock, ToolResultBlock

        patches: list[AgentBlockPatch] = []
        for block in content:
            if not isinstance(block, (ToolResultBlock, ServerToolResultBlock)):
                continue
            block_id = block.tool_use_id
            if block_id not in self._blocks:
                patches.append(self._start(block_id, "tool"))
            state = self._blocks[block_id]
            state["finished"] = True
            is_error = isinstance(block, ToolResultBlock) and bool(block.is_error)
            patches.append(
                AgentBlockPatch(
                    operation="finish",
                    block_id=block_id,
                    block_type="tool",
                    payload={
                        "tool_use_id": block_id,
                        "result": block.content,
                        "is_error": is_error,
                        "status": "failed" if is_error else "succeeded",
                    },
                )
            )
        return patches

    def finish_open(self, *, cancelled: bool = False) -> list[AgentBlockPatch]:
        patches: list[AgentBlockPatch] = []
        for block_id, state in self._blocks.items():
            if state["finished"]:
                continue
            state["finished"] = True
            patches.append(
                AgentBlockPatch(
                    operation="finish",
                    block_id=block_id,
                    block_type=state["kind"],
                    payload={"status": "cancelled" if cancelled else "completed"},
                )
            )
        return patches


def history_blocks(messages: list[SessionMessage]) -> list[dict[str, Any]]:
    """Return complete display blocks from SDK SessionMessage objects."""
    blocks: list[dict[str, Any]] = []
    tool_positions: dict[str, int] = {}
    for item in messages:
        message = item.message
        if not isinstance(message, Mapping):
            continue
        message_uuid = item.uuid
        role = item.type
        content = message.get("content")
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        if not isinstance(content, list):
            continue
        for index, raw in enumerate(content):
            if not isinstance(raw, Mapping):
                continue
            block_type = raw.get("type")
            if block_type in {"text", "thinking"}:
                blocks.append(
                    {
                        "block_id": f"{message_uuid}:{index}",
                        "block_type": block_type,
                        "message_uuid": message_uuid,
                        "role": role,
                        "status": "completed",
                        "text": raw.get("text") or raw.get("thinking") or "",
                        "payload": {},
                    }
                )
            elif block_type in {"tool_use", "server_tool_use"}:
                tool_id = str(raw.get("id") or f"{message_uuid}:{index}")
                tool_positions[tool_id] = len(blocks)
                blocks.append(
                    {
                        "block_id": tool_id,
                        "block_type": "tool",
                        "message_uuid": message_uuid,
                        "role": role,
                        "status": "running",
                        "text": "",
                        "payload": {
                            "tool_use_id": tool_id,
                            "name": raw.get("name"),
                            "input": raw.get("input") or {},
                        },
                    }
                )
            elif block_type in {"tool_result", "server_tool_result"}:
                tool_id = raw.get("tool_use_id")
                position = tool_positions.get(str(tool_id))
                if position is not None:
                    target = blocks[position]
                    target["status"] = "failed" if raw.get("is_error") else "completed"
                    target["payload"].update(
                        {
                            "result": raw.get("content"),
                            "is_error": bool(raw.get("is_error")),
                        }
                    )
    return blocks
