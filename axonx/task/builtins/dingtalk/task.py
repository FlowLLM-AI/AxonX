"""Built-in Task for sending DingTalk robot messages."""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from typing import Literal

from pydantic import Field

from ....components.registry import provider
from ....enums import TaskType
from ...core import BaseInputParams, BaseOutputParams, BaseTask, TaskStep
from .client import DingTalkClient


class DingTalkInputParams(BaseInputParams):
    """Message sent through the configured DingTalk application robot."""

    title: str = Field(min_length=1)
    text: str = Field(min_length=1)
    message_type: Literal["markdown", "text"] = "markdown"
    timeout: float = Field(default=10.0, gt=0)


class DingTalkOutputParams(BaseOutputParams):
    """Delivery references returned by DingTalk."""

    recipients: int = Field(ge=1)
    process_query_keys: list[str]


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _conversation_ids(value: str) -> tuple[str, ...]:
    try:
        conversations = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("DINGTALK_CONVERSATIONS must be a JSON object") from exc
    if not isinstance(conversations, dict) or not conversations:
        raise ValueError("DINGTALK_CONVERSATIONS must be a non-empty JSON object")
    if any(not isinstance(key, str) or not key.strip() for key in conversations):
        raise ValueError("DINGTALK_CONVERSATIONS keys must be non-empty strings")
    identifiers = tuple(conversations.values())
    if any(not isinstance(item, str) or not item.strip() for item in identifiers):
        raise ValueError("DINGTALK_CONVERSATIONS values must be non-empty strings")
    return tuple(dict.fromkeys(item.strip() for item in identifiers))


@provider("send_dingtalk_task")
class SendDingTalkTask(BaseTask):
    """Send one text or Markdown message to every configured DingTalk group."""

    task_type = TaskType.API
    input_cls = DingTalkInputParams
    output_cls = DingTalkOutputParams

    input_params: DingTalkInputParams

    def build_task_steps(self) -> Iterable[TaskStep]:
        yield self.send_message

    def send_message(self) -> None:
        conversations = _conversation_ids(_required_env("DINGTALK_CONVERSATIONS"))
        client = DingTalkClient(
            _required_env("DINGTALK_CLIENT_ID"),
            _required_env("DINGTALK_CLIENT_SECRET"),
            conversations,
            timeout=self.input_params.timeout,
        )
        keys = client.send(
            self.input_params.title,
            self.input_params.text,
            self.input_params.message_type,
        )
        self.state["recipients"] = len(conversations)
        self.state["process_query_keys"] = list(keys)

    def build_output_params(self) -> DingTalkOutputParams:
        return DingTalkOutputParams(
            recipients=self.state["recipients"],
            process_query_keys=self.state["process_query_keys"],
        )
