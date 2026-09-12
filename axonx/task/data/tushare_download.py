"""下载构建最小 A 股量化数据集所需的 Tushare 数据。"""

from __future__ import annotations

import os
from calendar import monthrange
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from functools import partial
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import field_validator

from ...components.component_registry import R
from ...enumeration import TaskType
from ...utils import TushareClient
from ..base_task import BaseConfig, BaseTask, TaskStep

HS300 = "000300.SH"
DATASETS = {
    "daily": (
        "ts_code",
        "trade_date",
        "open",
        "high",
        "low",
        "close",
        "pre_close",
        "change",
        "pct_chg",
        "vol",
        "amount",
    ),
    "adj_factor": ("ts_code", "trade_date", "adj_factor"),
    "index_weight": ("index_code", "con_code", "trade_date", "weight"),
}


class TushareDownloadConfig(BaseConfig):
    """下载日期范围；默认下载截至今天的最近七个自然日。"""

    start_date: str | None = None
    end_date: str | None = None
    days_back: int = 7
    timeout: int = 600

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def normalize_compact_date(cls, value: Any) -> Any:
        """Preserve YYYYMMDD values converted to integers by the generic CLI parser."""
        if isinstance(value, int) and not isinstance(value, bool):
            text = str(value)
            if len(text) == 8:
                return text
        return value


@R.register("download_tushar_task")
class DownloadTusharTask(BaseTask):
    """下载日线、复权因子和沪深300月度成分权重。"""

    config_cls = TushareDownloadConfig
    config: TushareDownloadConfig
    task_type = TaskType.INGESTION
    output_keys = ("start_date", "end_date", "files", "rows")

    def build_task_steps(self) -> Iterable[TaskStep]:
        yield self.initialize
        for day in self.context["days"]:
            yield partial(self.download_market_day, day)
        for start, end in self.context["months"]:
            yield partial(self.download_hs300_weight, start, end)

    def initialize(self) -> None:
        end = min(self._parse_date(self.config.end_date) or date.today(), date.today())
        if self.config.days_back <= 0:
            raise ValueError("days_back 必须大于 0")
        start = self._parse_date(self.config.start_date) or end - timedelta(days=self.config.days_back - 1)
        if start > end:
            raise ValueError("start_date 不能晚于 end_date")
        if self.config.timeout <= 0:
            raise ValueError("timeout 必须大于 0")

        days = tuple(start + timedelta(days=offset) for offset in range((end - start).days + 1))
        months = tuple(self._month_bounds(day) for day in days if day.day == 1 or day == start)
        self.context.update(
            client=TushareClient(timeout=self.config.timeout, logger=self.logger),
            root=Path(os.getenv("AXON_DATA_ROOT") or "axon_data").expanduser() / "data/data",
            days=days,
            months=months,
            start_date=f"{start:%Y%m%d}",
            end_date=f"{end:%Y%m%d}",
            files=[],
            rows=dict.fromkeys(DATASETS, 0),
        )

    def download_market_day(self, day: date) -> None:
        trade_date = f"{day:%Y%m%d}"
        daily = self._query("daily", trade_date=trade_date)
        if daily.empty:
            return
        self._save("daily", daily, day)
        self._save("adj_factor", self._query("adj_factor", trade_date=trade_date), day)

    def download_hs300_weight(self, start: date, end: date) -> None:
        frame = self._query(
            "index_weight",
            index_code=HS300,
            start_date=f"{start:%Y%m%d}",
            end_date=f"{end:%Y%m%d}",
        )
        if frame.empty:
            return
        for trade_date, group in frame.groupby("trade_date", sort=True):
            self._save("index_weight", group, self._parse_date(trade_date))

    def _query(self, api_name: str, **params: Any) -> pd.DataFrame:
        fields = ",".join(DATASETS[api_name])
        frame = self.context["client"].query(api_name, fields=fields, **params)
        missing = set(DATASETS[api_name]).difference(frame.columns)
        if not frame.empty and missing:
            raise RuntimeError(f"{api_name} 缺少字段: {sorted(missing)}")
        return frame

    def _save(self, api_name: str, frame: pd.DataFrame, day: date) -> None:
        if frame.empty:
            return
        sort_columns = [column for column in DATASETS[api_name] if column in frame.columns]
        frame = frame.loc[:, DATASETS[api_name]].sort_values(sort_columns, kind="stable", ignore_index=True)
        path = self.context["root"] / f"{day:%Y}" / f"{day:%Y%m%d}" / f"{api_name}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        try:
            frame.to_parquet(temporary, index=False, compression="zstd", compression_level=6)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        self.context["files"].append(str(path))
        self.context["rows"][api_name] += len(frame)

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        if value in (None, ""):
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        text = str(value).strip()
        return datetime.strptime(text, "%Y%m%d" if text.isdigit() else "%Y-%m-%d").date()

    @staticmethod
    def _month_bounds(day: date) -> tuple[date, date]:
        start = day.replace(day=1)
        return start, start.replace(day=monthrange(start.year, start.month)[1])
