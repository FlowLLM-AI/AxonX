"""Project Claude SDK messages into stable, UI-oriented block patches."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from typing import Any, Mapping

from ...job.events import AgentBlockPatch


def sdk_value(value: Any) -> Any:
    """Serialize SDK dataclasses losslessly while retaining nested type names."""
    if is_dataclass(value) and not isinstance(value, type):
        return {
            "type_name": type(value).__name__,
            **{field.name: sdk_value(getattr(value, field.name)) for field in fields(value)},
        }
    if isinstance(value, Mapping):
        return {key: sdk_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [sdk_value(item) for item in value]
    return value


def message_payload(message: Any) -> dict[str, Any]:
    if not is_dataclass(message):
        raise TypeError(f"Unsupported Claude message: {type(message).__name__}")
    return {field.name: sdk_value(getattr(message, field.name)) for field in fields(message)}


class ClaudeMessageProjector:
    """Stateful projection for one streamed Claude turn."""

    def __init__(self) -> None:
        self._blocks: dict[str, dict[str, Any]] = {}
        self._indices: dict[int, str] = {}
        self._tools: dict[str, str] = {}

    @staticmethod
    def _kind(block: Mapping[str, Any]) -> str | None:
        name = block.get("type_name") or block.get("type")
        return {
            "TextBlock": "text",
            "text": "text",
            "ThinkingBlock": "thinking",
            "thinking": "thinking",
            "ToolUseBlock": "tool",
            "tool_use": "tool",
            "ServerToolUseBlock": "tool",
            "server_tool_use": "tool",
        }.get(str(name))

    @staticmethod
    def _content(block: Mapping[str, Any], kind: str) -> str:
        if kind == "text":
            return str(block.get("text") or "")
        if kind == "thinking":
            return str(block.get("thinking") or "")
        return ""

    def _start(
        self, block_id: str, kind: str, *, payload: dict[str, Any] | None = None
    ) -> AgentBlockPatch:
        self._blocks[block_id] = {"kind": kind, "text": "", "finished": False}
        return AgentBlockPatch(
            operation="start", block_id=block_id, block_type=kind, payload=payload or {}
        )

    def project(self, message: Any) -> list[AgentBlockPatch]:
        from claude_agent_sdk import AssistantMessage, StreamEvent, UserMessage

        if isinstance(message, StreamEvent):
            return self._stream(message.uuid, message.event)
        if isinstance(message, AssistantMessage):
            return self._assistant(message.uuid or message.message_id or "assistant", message.content)
        if isinstance(message, UserMessage) and isinstance(message.content, list):
            return self._tool_results(message.content)
        return []

    def _stream(self, message_uuid: str, event: Mapping[str, Any]) -> list[AgentBlockPatch]:
        event_type = event.get("type")
        index = event.get("index")
        if not isinstance(index, int):
            return []
        if event_type == "content_block_start":
            block = event.get("content_block")
            if not isinstance(block, Mapping):
                return []
            kind = self._kind(block)
            if kind is None:
                return []
            tool_id = block.get("id") if kind == "tool" else None
            block_id = str(tool_id or f"{message_uuid}:{index}")
            self._indices[index] = block_id
            if isinstance(tool_id, str):
                self._tools[tool_id] = block_id
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
            return [self._start(block_id, kind, payload=payload)]
        block_id = self._indices.get(index)
        if block_id is None:
            return []
        state = self._blocks[block_id]
        if event_type == "content_block_delta":
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
        if event_type == "content_block_stop":
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
            return [
                AgentBlockPatch(
                    operation="finish", block_id=block_id, block_type=state["kind"]
                )
            ]
        return []

    def _assistant(self, message_uuid: str, content: list[Any]) -> list[AgentBlockPatch]:
        patches: list[AgentBlockPatch] = []
        for index, raw in enumerate(content):
            block = sdk_value(raw)
            if not isinstance(block, Mapping):
                continue
            kind = self._kind(block)
            if kind is None:
                continue
            tool_id = block.get("id") if kind == "tool" else None
            block_id = str(tool_id or self._indices.get(index) or f"{message_uuid}:{index}")
            if isinstance(tool_id, str):
                self._tools[tool_id] = block_id
            if block_id not in self._blocks:
                payload = (
                    {
                        "tool_use_id": tool_id,
                        "name": block.get("name"),
                        "input": block.get("input") or {},
                        "status": "running",
                    }
                    if kind == "tool"
                    else {}
                )
                patches.append(self._start(block_id, kind, payload=payload))
            state = self._blocks[block_id]
            complete = self._content(block, kind)
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
                patches.append(
                    AgentBlockPatch(
                        operation="finish", block_id=block_id, block_type=kind
                    )
                )
        return patches

    def _tool_results(self, content: list[Any]) -> list[AgentBlockPatch]:
        patches: list[AgentBlockPatch] = []
        for raw in content:
            block = sdk_value(raw)
            if not isinstance(block, Mapping) or block.get("type_name") not in {
                "ToolResultBlock",
                "ServerToolResultBlock",
            }:
                continue
            tool_id = block.get("tool_use_id")
            if not isinstance(tool_id, str):
                continue
            block_id = self._tools.get(tool_id)
            if block_id is None:
                block_id = tool_id
                patches.append(self._start(block_id, "tool"))
            state = self._blocks[block_id]
            state["finished"] = True
            patches.append(
                AgentBlockPatch(
                    operation="finish",
                    block_id=block_id,
                    block_type="tool",
                    payload={
                        "tool_use_id": tool_id,
                        "result": block.get("content"),
                        "is_error": bool(block.get("is_error")),
                        "status": "failed" if block.get("is_error") else "succeeded",
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


def history_blocks(messages: list[Any]) -> list[dict[str, Any]]:
    """Return complete display blocks from SDK SessionMessage objects."""
    blocks: list[dict[str, Any]] = []
    tool_positions: dict[str, int] = {}
    for item in messages:
        message = item.message if hasattr(item, "message") else item.get("message")
        if not isinstance(message, Mapping):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for raw in content:
            if not isinstance(raw, Mapping):
                continue
            block_type = raw.get("type")
            if block_type in {"text", "thinking"}:
                blocks.append(
                    {
                        "block_id": f"{item.uuid}:{len(blocks)}",
                        "block_type": block_type,
                        "status": "completed",
                        "text": raw.get("text") or raw.get("thinking") or "",
                        "payload": {},
                    }
                )
            elif block_type in {"tool_use", "server_tool_use"}:
                tool_id = str(raw.get("id") or f"{item.uuid}:{len(blocks)}")
                tool_positions[tool_id] = len(blocks)
                blocks.append(
                    {
                        "block_id": tool_id,
                        "block_type": "tool",
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
                        {"result": raw.get("content"), "is_error": bool(raw.get("is_error"))}
                    )
    return blocks
