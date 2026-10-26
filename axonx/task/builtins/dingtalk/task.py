"""Built-in Task for sending DingTalk robot messages."""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import Field

from ...core.base import BaseTask, TaskStep
from ...models.identity import TaskType
from ...models.params import BaseInputParams, BaseOutputParams
from .client import DingTalkMessageType, send_dingtalk_message


class DingTalkInputParams(BaseInputParams):
    """Message sent through the configured DingTalk application robot."""

    title: str = Field(min_length=1)
    text: str = Field(min_length=1)
    message_type: DingTalkMessageType = "markdown"
    timeout: float = Field(default=10.0, gt=0)


class DingTalkOutputParams(BaseOutputParams):
    """Delivery references returned by DingTalk."""

    recipients: int = Field(ge=1)
    process_query_keys: list[str]


class SendDingTalkTask(BaseTask):
    """Send one text or Markdown message to every configured DingTalk group."""

    task_type = TaskType.API
    input_cls = DingTalkInputParams
    output_cls = DingTalkOutputParams

    input_params: DingTalkInputParams

    def build_task_steps(self) -> Iterable[TaskStep]:
        yield self.send_message

    def send_message(self) -> None:
        keys = send_dingtalk_message(
            self.input_params.title,
            self.input_params.text,
            self.input_params.message_type,
            timeout=self.input_params.timeout,
        )
        self.state["recipients"] = len(keys)
        self.state["process_query_keys"] = list(keys)

    def build_output_params(self) -> DingTalkOutputParams:
        return DingTalkOutputParams(
            recipients=self.state["recipients"],
            process_query_keys=self.state["process_query_keys"],
        )
