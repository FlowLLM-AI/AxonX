"""Download selection, deterministic dataset persistence and failure cleanup."""

from datetime import date

import pandas as pd
import pytest

from axonx.task.builtins.tushare import data
from axonx.task.builtins.tushare import task as download
from axonx.task.runtime.executor import TaskExecutor


def test_download_task_writes_selected_partitions_and_closes_client(monkeypatch, tmp_path):
    clients = []

    class Client:
        def __init__(self, **_kwargs):
            self.closed = False
            self.calls = []
            clients.append(self)

        def query(self, name, fields, **params):
            self.calls.append((name, params))
            if name == "index_weight":
                return pd.DataFrame(
                    [{"index_code": "000300.SH", "con_code": "A", "trade_date": params["start_date"], "weight": 100.0}]
                )
            symbols = ["B", "A"] if name in {"daily", "stk_limit", "adj_factor"} else ["A"]
            return pd.DataFrame(
                [
                    {
                        column: code if column == "ts_code" else params.get("trade_date", "value")
                        for column in fields.split(",")
                    }
                    for code in symbols
                ]
            )

        query_has_more = query

        def close(self):
            self.closed = True

    monkeypatch.setattr(download, "TushareClient", Client)
    task = download.DownloadTushareTask(
        {"start_date": 20240131, "end_date": "2024-02-01"},
        workspace_path=tmp_path,
        reg_name="download",
    )
    TaskExecutor().execute(task)
    assert clients[0].closed
    output = task.output_params
    assert (output.start_date, output.end_date) == ("20240131", "20240201")
    assert len(output.files) == 11
    assert output.rows == {
        "stock_basic": 1,
        "namechange": 1,
        "trade_cal": 1,
        "stk_limit": 4,
        "daily": 4,
        "adj_factor": 4,
        "index_weight": 2,
    }
    saved = pd.read_parquet(tmp_path / "tushare/2024/20240131/daily.parquet")
    assert saved.columns.to_list() == list(data.DATASETS["daily"])
    assert saved["ts_code"].to_list() == ["A", "B"]
    assert [params["list_status"] for name, params in clients[0].calls if name == "stock_basic"] == list(
        data.STOCK_LIST_STATUSES
    )


def test_store_keeps_daily_duplicates_and_records_only_successful_writes(monkeypatch, tmp_path):
    store = data.TushareDatasetStore(tmp_path)
    row = {column: "A" for column in data.DATASETS["adj_factor"]}
    with pytest.raises(ValueError, match="requires a partition date"):
        store.save("adj_factor", pd.DataFrame([row]))
    assert store.files == []
    store.save("adj_factor", pd.DataFrame([row, row]), date(2024, 1, 1))
    assert store.rows["adj_factor"] == 2
    assert len(pd.read_parquet(store.files[0])) == 2

    def fail(*_args, **_kwargs):
        raise OSError("disk unavailable")

    monkeypatch.setattr(data, "atomic_write", fail)
    with pytest.raises(OSError, match="disk unavailable"):
        store.save("adj_factor", pd.DataFrame([row]), date(2024, 1, 2))
    assert store.rows["adj_factor"] == 2
    assert len(store.files) == 1


def test_download_failure_still_closes_client(monkeypatch, tmp_path):
    class Client:
        closed = False

        def query(self, *_args, **_kwargs):
            return pd.DataFrame({"unexpected": [1]})

        def close(self):
            self.closed = True

    client = Client()
    monkeypatch.setattr(download, "TushareClient", lambda **_: client)
    task = download.DownloadTushareTask(
        {"start_date": "20240101", "end_date": "20240101", "datasets": ["daily"]},
        workspace_path=tmp_path,
        reg_name="download",
    )
    with pytest.raises(RuntimeError, match="缺少字段"):
        TaskExecutor().execute(task)
    assert client.closed
