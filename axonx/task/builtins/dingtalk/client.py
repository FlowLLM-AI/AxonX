"""DingTalk application-robot client owned by the notification Task."""

from __future__ import annotations

import json
import os
from contextlib import nullcontext
from typing import Literal

import httpx

DingTalkMessageType = Literal["markdown", "text"]
TOKEN_URL = "https://api.dingtalk.com/v1.0/oauth2/accessToken"
MESSAGE_URL = "https://api.dingtalk.com/v1.0/robot/groupMessages/send"


def _json(response: httpx.Response) -> dict:
    try:
        body = response.json()
    except ValueError as exc:
        raise RuntimeError("DingTalk returned invalid JSON") from exc
    if not isinstance(body, dict):
        raise TypeError("DingTalk returned an invalid response object")
    return body


class DingTalkClient:
    """Authenticate once and send one message to configured conversations."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        conversation_ids: tuple[str, ...],
        *,
        timeout: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        if not client_id.strip() or not client_secret.strip():
            raise ValueError("DingTalk credentials must be non-empty")
        if not conversation_ids or any(not value.strip() for value in conversation_ids):
            raise ValueError("DingTalk conversation IDs must be non-empty")
        if timeout <= 0:
            raise ValueError("DingTalk timeout must be greater than 0")
        self.client_id = client_id
        self.client_secret = client_secret
        self.conversation_ids = tuple(dict.fromkeys(conversation_ids))
        self.timeout = timeout
        self.client = client

    @classmethod
    def from_env(cls, *, timeout: float = 10.0) -> DingTalkClient:
        """Read application credentials and named conversations from the environment."""
        conversations = _conversation_ids(_required_env("DINGTALK_CONVERSATIONS"))
        return cls(
            _required_env("DINGTALK_CLIENT_ID"),
            _required_env("DINGTALK_CLIENT_SECRET"),
            conversations,
            timeout=timeout,
        )

    def send(
        self,
        title: str,
        text: str,
        message_type: DingTalkMessageType = "markdown",
    ) -> tuple[str, ...]:
        """Send a text or Markdown message and return process query keys."""
        messages = {
            "markdown": ("sampleMarkdown", {"title": title, "text": text}),
            "text": ("sampleText", {"content": text}),
        }
        if message_type not in messages:
            raise ValueError(f"Unsupported message type: {message_type}")

        with nullcontext(self.client) if self.client is not None else httpx.Client(timeout=self.timeout) as client:
            token = self._access_token(client)
            msg_key, msg_param = messages[message_type]
            keys: list[str] = []
            failures: list[str] = []
            for index, conversation_id in enumerate(self.conversation_ids, 1):
                try:
                    response = client.post(
                        MESSAGE_URL,
                        headers={"x-acs-dingtalk-access-token": token},
                        json={
                            "robotCode": self.client_id,
                            "openConversationId": conversation_id,
                            "msgKey": msg_key,
                            "msgParam": json.dumps(msg_param, ensure_ascii=False),
                        },
                    )
                    response.raise_for_status()
                    key = _json(response).get("processQueryKey")
                    if not isinstance(key, str) or not key:
                        raise RuntimeError("response did not contain processQueryKey")
                    keys.append(key)
                except (httpx.HTTPError, RuntimeError, TypeError, ValueError) as exc:
                    failures.append(f"group[{index}]: {type(exc).__name__}")
            if failures:
                raise RuntimeError("Failed to send DingTalk message: " + "; ".join(failures))
            return tuple(keys)

    def _access_token(self, client: httpx.Client) -> str:
        try:
            response = client.post(
                TOKEN_URL,
                json={"appKey": self.client_id, "appSecret": self.client_secret},
            )
            response.raise_for_status()
            token = _json(response).get("accessToken")
        except (httpx.HTTPError, RuntimeError, TypeError, ValueError) as exc:
            raise RuntimeError(f"Failed to obtain DingTalk access token: {type(exc).__name__}") from exc
        if not isinstance(token, str) or not token:
            raise RuntimeError("DingTalk access token response did not contain a token")
        return token


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


def send_dingtalk_message(
    title: str,
    text: str,
    message_type: DingTalkMessageType = "markdown",
    *,
    timeout: float = 10.0,
) -> tuple[str, ...]:
    """Send a message using validated environment configuration."""
    return DingTalkClient.from_env(timeout=timeout).send(title, text, message_type)
