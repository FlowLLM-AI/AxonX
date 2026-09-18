"""Regression tests for Tushare retry behavior."""

from __future__ import annotations

from axonx.utils.connectors import tushare as tushare_module
from axonx.utils.connectors.tushare import TushareClient


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


def test_tushare_frequency_limit_waits_and_retries(monkeypatch):
    session = FakeSession(
        [
            {
                "code": -1,
                "msg": "抱歉，您访问接口(stk_limit)频率超限(500次/分钟)。",
            },
            {
                "code": -1,
                "msg": "抱歉，您访问接口(stk_limit)频率超限(500次/分钟)。",
            },
            {
                "code": 0,
                "data": {
                    "fields": ["ts_code", "trade_date"],
                    "items": [["000001.SZ", "20260914"]],
                    "has_more": False,
                },
            },
        ],
    )
    waits = []
    monkeypatch.setattr(tushare_module.time, "sleep", waits.append)
    client = TushareClient(session=session, transient_error_retries=0)

    frame = client.query("stk_limit", fields="ts_code,trade_date", trade_date="20260914")

    assert session.calls == 3
    assert waits == [300.0, 300.0]
    assert frame.to_dict("records") == [
        {"ts_code": "000001.SZ", "trade_date": "20260914"},
    ]
