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


def test_tushare_unlimited_rate_retries_keep_fixed_wait():
    limited = {"code": -1, "msg": "频率超限"}
    success = {"code": 0, "data": {"fields": ["id"], "items": [[1]]}}
    session = FakeSession([limited] * 15 + [success])
    waits = []
    client = TushareClient(
        session=session,
        retry_rate_limit_forever=True,
        rate_limit_retry_seconds=60,
        sleep=waits.append,
    )
    assert client.query("daily")["id"].tolist() == [1]
    assert waits == [60] * 15


def test_tushare_deadline_caps_retry_and_is_not_sent_as_api_parameter():
    from datetime import UTC, datetime, timedelta
    from axonx.task.contracts import DeadlineBudget, WindowClock

    class Clock(WindowClock):
        elapsed = 0

        def now(self):
            return datetime(2024, 1, 1, tzinfo=UTC) + timedelta(seconds=self.elapsed)

        def monotonic(self):
            return self.elapsed

        def sleep(self, seconds):
            self.elapsed += seconds

    clock = Clock()
    budget = DeadlineBudget(clock, clock.now() + timedelta(seconds=3))
    calls = []

    class Session(FakeSession):
        def post(self, *args, **kwargs):
            calls.append(kwargs)
            return super().post(*args, **kwargs)

    client = TushareClient(
        session=Session([{"code": -1, "msg": "频率超限"}]),
        retry_rate_limit_forever=True,
    )
    with pytest.raises(TimeoutError, match="deadline"):
        client.query("daily", budget=budget)
    assert clock.elapsed == 3
    assert calls[0]["timeout"] == 3
    assert "budget" not in calls[0]["json"]["params"]


def test_tushare_closes_owned_session_only(monkeypatch):
    from types import SimpleNamespace

    closed = []
    session = SimpleNamespace(close=lambda: closed.append(True))
    monkeypatch.setattr("requests.Session", lambda: session)
    TushareClient().close()
    assert closed == [True]
    TushareClient(session=session).close()
    assert closed == [True]


@pytest.mark.parametrize("phase", ["json", "frame"])
def test_tushare_rejects_results_that_expire_during_decoding(monkeypatch, phase):
    from types import SimpleNamespace
    import pandas as pd

    budget = SimpleNamespace(remaining_seconds=1)
    payload = {"code": 0, "data": {"fields": ["id"], "items": [[1]]}}

    class Response(FakeResponse):
        def json(self):
            if phase == "json":
                budget.remaining_seconds = 0
            return self.payload

    class Session:
        def post(self, *args, **kwargs):
            return Response(payload)

    original = pd.DataFrame

    def frame(*args, **kwargs):
        value = original(*args, **kwargs)
        if phase == "frame":
            budget.remaining_seconds = 0
        return value

    monkeypatch.setattr(pd, "DataFrame", frame)
    with pytest.raises(TimeoutError, match="deadline"):
        TushareClient(session=Session()).query("daily", budget=budget)
