"""DingTalk application-robot client owned by the notification Task."""

from __future__ import annotations

import json
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

        client = self.client or httpx.Client(timeout=self.timeout)
        owned = self.client is None
        try:
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
                raise RuntimeError(
                    "Failed to send DingTalk message: " + "; ".join(failures)
                )
            return tuple(keys)
        finally:
            if owned:
                client.close()

    def _access_token(self, client: httpx.Client) -> str:
        try:
            response = client.post(
                TOKEN_URL,
                json={"appKey": self.client_id, "appSecret": self.client_secret},
            )
            response.raise_for_status()
            token = _json(response).get("accessToken")
        except (httpx.HTTPError, RuntimeError, TypeError, ValueError) as exc:
            raise RuntimeError(
                f"Failed to obtain DingTalk access token: {type(exc).__name__}"
            ) from exc
        if not isinstance(token, str) or not token:
            raise RuntimeError("DingTalk access token response did not contain a token")
        return token
