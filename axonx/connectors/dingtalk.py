"""DingTalk application-robot connector."""

from __future__ import annotations

import json
import os
from typing import Any, Literal

import httpx

from ..utils.env import load_env

DingTalkMessageType = Literal["markdown", "text"]
TOKEN_URL = "https://api.dingtalk.com/v1.0/oauth2/accessToken"
MESSAGE_URL = "https://api.dingtalk.com/v1.0/robot/groupMessages/send"


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _conversation_ids() -> tuple[str, ...]:
    try:
        conversations = json.loads(_required_env("DINGTALK_CONVERSATIONS"))
    except json.JSONDecodeError as exc:
        raise ValueError("DINGTALK_CONVERSATIONS must be a JSON object") from exc
    if not isinstance(conversations, dict) or not conversations:
        raise ValueError("DINGTALK_CONVERSATIONS must be a non-empty JSON object")
    if any(not isinstance(key, str) or not key.strip() for key in conversations):
        raise ValueError("DINGTALK_CONVERSATIONS keys must be non-empty strings")
    if any(
        not isinstance(value, str) or not value.strip()
        for value in conversations.values()
    ):
        raise ValueError("DINGTALK_CONVERSATIONS values must be non-empty strings")
    return tuple(dict.fromkeys(value.strip() for value in conversations.values()))


def _json(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise RuntimeError("DingTalk returned invalid JSON") from exc
    if not isinstance(body, dict):
        raise RuntimeError("DingTalk returned an invalid response object")
    return body


def _access_token(client_id: str, client_secret: str, timeout: float) -> str:
    try:
        response = httpx.post(
            TOKEN_URL,
            json={"appKey": client_id, "appSecret": client_secret},
            timeout=timeout,
        )
        response.raise_for_status()
        token = _json(response).get("accessToken")
    except Exception as exc:  # Do not expose credentials stored on the request.
        raise RuntimeError(
            f"Failed to obtain DingTalk access token: {type(exc).__name__}"
        ) from exc
    if not isinstance(token, str) or not token:
        raise RuntimeError("DingTalk access token response did not contain a token")
    return token


def send_dingtalk_message(
    title: str,
    text: str,
    msgtype: DingTalkMessageType = "markdown",
    timeout: float = 10.0,
) -> str:
    """Send a text or Markdown message to every configured DingTalk group."""
    messages = {
        "markdown": ("sampleMarkdown", {"title": title, "text": text}),
        "text": ("sampleText", {"content": text}),
    }
    if msgtype not in messages:
        raise ValueError(f"Unsupported message type: {msgtype}")

    load_env()
    client_id = _required_env("DINGTALK_CLIENT_ID")
    conversation_ids = _conversation_ids()
    token = _access_token(client_id, _required_env("DINGTALK_CLIENT_SECRET"), timeout)
    msg_key, msg_param = messages[msgtype]
    responses: list[str] = []
    failures: list[str] = []

    for index, conversation_id in enumerate(conversation_ids, 1):
        try:
            response = httpx.post(
                MESSAGE_URL,
                headers={"x-acs-dingtalk-access-token": token},
                json={
                    "robotCode": client_id,
                    "openConversationId": conversation_id,
                    "msgKey": msg_key,
                    "msgParam": json.dumps(msg_param, ensure_ascii=False),
                },
                timeout=timeout,
            )
            response.raise_for_status()
            if not isinstance(_json(response).get("processQueryKey"), str):
                raise RuntimeError("response did not contain processQueryKey")
            responses.append(response.text)
        except (
            Exception
        ) as exc:  # Try all groups without exposing IDs or request headers.
            failures.append(f"group[{index}]: {type(exc).__name__}")

    if failures:
        raise RuntimeError("Failed to send DingTalk message: " + "; ".join(failures))
    return "\n".join(responses)
