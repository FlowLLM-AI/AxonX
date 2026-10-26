"""Built-in API protocol handling, pagination and resource ownership."""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import httpx
import pytest
import requests

from axonx.task.builtins.dingtalk import client as dingtalk
from axonx.task.builtins.dingtalk.task import SendDingTalkTask
from axonx.task.builtins.tushare.client import TushareClient
from axonx.task.core.clock import DeadlineBudget, WindowClock
from axonx.task.runtime.executor import TaskExecutor


def test_notification_task_loads_environment_and_closes_owned_transport(monkeypatch, tmp_path):
    monkeypatch.setenv("DINGTALK_CLIENT_ID", "app")
    monkeypatch.setenv("DINGTALK_CLIENT_SECRET", "secret")
    monkeypatch.setenv("DINGTALK_CONVERSATIONS", '{"one":" A ","duplicate":"A","two":"B"}')
    sent = []

    def respond(request):
        body = json.loads(request.content)
        if str(request.url) == dingtalk.TOKEN_URL:
            assert body == {"appKey": "app", "appSecret": "secret"}
            return httpx.Response(200, json={"accessToken": "token"})
        assert request.headers["x-acs-dingtalk-access-token"] == "token"
        assert json.loads(body["msgParam"]) == {"title": "标题", "text": "内容"}
        sent.append(body["openConversationId"])
        return httpx.Response(200, json={"processQueryKey": body["openConversationId"]})

    transport = httpx.Client(transport=httpx.MockTransport(respond))
    monkeypatch.setattr(dingtalk.httpx, "Client", lambda **_: transport)
    task = SendDingTalkTask({"title": "标题", "text": "内容"}, workspace_path=tmp_path, reg_name="notify")
    TaskExecutor().execute(task)
    assert sent == ["A", "B"]
    assert task.output_params.recipients == 2
    assert task.output_params.process_query_keys == ["A", "B"]
    assert transport.is_closed


def test_notification_attempts_every_group_and_keeps_injected_transport_open():
    sent = []

    def respond(request):
        if str(request.url) == dingtalk.TOKEN_URL:
            return httpx.Response(200, json={"accessToken": "token"})
        group = json.loads(request.content)["openConversationId"]
        sent.append(group)
        return httpx.Response(200, json={} if group == "A" else {"processQueryKey": "ok"})

    with httpx.Client(transport=httpx.MockTransport(respond)) as transport:
        client = dingtalk.DingTalkClient("app", "secret", ("A", "B"), client=transport)
        with pytest.raises(RuntimeError, match=r"group\[1\]: RuntimeError"):
            client.send("title", "body", "text")
        assert sent == ["A", "B"]
        assert not transport.is_closed


@pytest.mark.parametrize("conversations", ["[]", "{}", '{"name": " "}', '{" ":"A"}', '{"name": 1}', "invalid"])
def test_notification_rejects_invalid_configuration(monkeypatch, conversations):
    monkeypatch.setenv("DINGTALK_CONVERSATIONS", conversations)
    with pytest.raises(ValueError, match="DINGTALK_CONVERSATIONS"):
        dingtalk.DingTalkClient.from_env()


def response(items, *, has_more=False):
    result = Mock()
    result.json.return_value = {"code": 0, "data": {"fields": ["id", "value"], "items": items, "has_more": has_more}}
    return result


def test_tushare_pagination_advances_offsets_and_removes_overlap():
    session = Mock(spec=requests.Session)
    session.post.side_effect = [response([[1, "a"], [2, "b"]], has_more=True), response([[2, "b"], [3, "c"]])]
    client = TushareClient(session=session)
    frame = client.query_has_more("daily", limit=2, overlap=0.5)
    assert frame["id"].to_list() == [1, 2, 3]
    assert [call.kwargs["json"]["params"]["offset"] for call in session.post.call_args_list] == [0, 1]
    client.close()
    session.close.assert_not_called()


@pytest.mark.parametrize("empty", [False, True])
def test_tushare_rejects_pages_that_do_not_advance(empty):
    session = Mock(spec=requests.Session)
    page = response([] if empty else [[1, "a"]], has_more=True)
    session.post.return_value = page
    client = TushareClient(session=session)
    with pytest.raises(RuntimeError, match="pagination made no progress"):
        client.query_has_more("daily")
    assert session.post.call_count == (1 if empty else 2)


def test_tushare_rejects_incomplete_unpaginated_responses():
    session = Mock(spec=requests.Session)
    session.post.return_value = response([[1, "a"]], has_more=True)
    with pytest.raises(RuntimeError, match="incomplete"):
        TushareClient(session=session).query("daily")


def test_tushare_retry_waits_and_timeouts_share_the_deadline():
    class Clock(WindowClock):
        elapsed = 0.0

        def now(self):
            return datetime(2024, 1, 1, tzinfo=UTC)

        def monotonic(self):
            return self.elapsed

        def sleep(self, seconds):
            self.elapsed += seconds

    clock = Clock()
    budget = DeadlineBudget(clock, clock.now() + timedelta(seconds=5))
    session = Mock(spec=requests.Session)
    session.post.side_effect = requests.Timeout("offline")
    client = TushareClient(session=session, transient_error_retry_initial_seconds=3)
    with pytest.raises(TimeoutError, match="deadline exceeded"):
        client.query("daily", budget=budget)
    assert clock.elapsed == 5
    assert [call.kwargs["timeout"] for call in session.post.call_args_list] == [5.0, 2.0]


def test_tushare_closes_only_sessions_it_creates(monkeypatch):
    session = Mock(spec=requests.Session)
    monkeypatch.setattr(requests, "Session", lambda: session)
    TushareClient().close()
    session.close.assert_called_once()
