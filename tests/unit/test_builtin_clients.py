"""Regression tests for clients owned by built-in Tasks."""

from __future__ import annotations

import httpx
import pytest

from axonx.task.builtins.dingtalk import DingTalkClient
from axonx.task.builtins.tushare import TushareClient


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payloads):
        self.payloads = iter(payloads)
        self.calls = 0

    def post(self, *_args, **_kwargs):
        self.calls += 1
        return FakeResponse(next(self.payloads))


def test_tushare_limit_retries_are_bounded():
    limited = {"code": -1, "msg": "频率超限"}
    session = FakeSession([limited, limited, limited])
    waits: list[float] = []
    client = TushareClient(
        session=session,
        transient_error_retries=0,
        limit_error_retries=2,
        transient_error_retry_max_seconds=1,
        sleep=waits.append,
    )

    with pytest.raises(RuntimeError, match="retry budget exhausted"):
        client.query("daily")

    assert session.calls == 3
    assert waits == [1, 1]


def test_tushare_pagination_detects_no_progress():
    page = {
        "code": 0,
        "data": {"fields": ["id"], "items": [[1]], "has_more": True},
    }
    client = TushareClient(session=FakeSession([page, page]), sleep=lambda _: None)

    with pytest.raises(RuntimeError, match="made no progress"):
        client.query_has_more("items", limit=1)


def test_dingtalk_client_returns_structured_delivery_keys():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("accessToken"):
            return httpx.Response(200, json={"accessToken": "token"})
        return httpx.Response(200, json={"processQueryKey": "delivery"})

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as http_client:
        client = DingTalkClient("app", "secret", ("conversation",), client=http_client)
        assert client.send("title", "body") == ("delivery",)
