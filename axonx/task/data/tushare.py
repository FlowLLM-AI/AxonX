"""下载构建最小 A 股量化数据集所需的 Tushare 数据。"""

from __future__ import annotations

import os
from calendar import monthrange
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import field_validator

from ...components.registry import R
from ...connectors.tushare import TushareClient
from ...enums import TaskType
from ...utils.fs import atomic_write
from ..base import BaseInputParams, BaseOutputParams, BaseTask, TaskStep

HS300 = "000300.SH"
DOWNLOAD_GROUPS = ("static", "stk_limit", "daily", "adj_factor", "index_weight")
DEFAULT_DOWNLOAD_GROUPS = DOWNLOAD_GROUPS
STATIC_DATASETS = ("stock_basic", "namechange", "trade_cal")
STOCK_LIST_STATUSES = ("L", "D", "P", "G")
DATASETS = {
    "stock_basic": (
        "ts_code",
        "symbol",
        "name",
        "market",
        "exchange",
        "list_status",
        "list_date",
        "delist_date",
    ),
    "namechange": (
        "ts_code",
        "name",
        "start_date",
        "end_date",
        "ann_date",
        "change_reason",
    ),
    "trade_cal": ("exchange", "cal_date", "is_open", "pretrade_date"),
    "stk_limit": ("ts_code", "trade_date", "up_limit", "down_limit"),
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


class TushareDownloadInputParams(BaseInputParams):
    """下载日期范围；start_date 未设置时下载截至 end_date 的最近若干自然日。"""

    start_date: str | None = None
    end_date: str | None = None
    days_back: int = 7
    timeout: int = 600
    datasets: str = ",".join(DEFAULT_DOWNLOAD_GROUPS)

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def normalize_compact_date(cls, value: Any) -> Any:
        """Preserve YYYYMMDD values converted to integers by the generic CLI parser."""
        if isinstance(value, int) and not isinstance(value, bool):
            text = str(value)
            if len(text) == 8:
                return text
        return value

    @field_validator("datasets", mode="before")
    @classmethod
    def normalize_datasets(cls, value: Any) -> str:
        """Accept a comma-separated string or a JSON list from the CLI."""
        if isinstance(value, (list, tuple)):
            value = ",".join(str(item) for item in value)
        if not isinstance(value, str):
            raise ValueError("datasets 必须是逗号分隔字符串或字符串列表")
        selected = tuple(dict.fromkeys(item.strip() for item in value.split(",") if item.strip()))
        if not selected:
            raise ValueError("datasets 不能为空")
        unknown = sorted(set(selected) - set(DOWNLOAD_GROUPS))
        if unknown:
            raise ValueError(f"不支持的 datasets: {unknown}; 可选值: {list(DOWNLOAD_GROUPS)}")
        return ",".join(selected)


class TushareDownloadOutputParams(BaseOutputParams):
    start_date: str
    end_date: str
    files: list[str]
    rows: dict[str, int]


@R.register("download_tushare_task")
class DownloadTushareTask(BaseTask):
    """下载构建最小 A 股量化数据集所需的 Tushare 数据。

    static、stk_limit、daily、adj_factor 和 index_weight 是可独立选择的下载步骤。
    任务按日期下载日频数据，并按月查询沪深 300 成分权重。
    所有结果经过字段检查和稳定排序后，以 Parquet 格式原子写入工作区的
    ``tushare/<年份>/<交易日>`` 目录，同时返回文件清单和各数据集行数。
    """

    task_type = TaskType.API

    input_cls = TushareDownloadInputParams
    output_cls = TushareDownloadOutputParams

    def build_output_params(self) -> TushareDownloadOutputParams:
        return TushareDownloadOutputParams(
            start_date=self.context["start_date"],
            end_date=self.context["end_date"],
            files=self.context["files"],
            rows=self.context["rows"],
        )
    input_params: TushareDownloadInputParams

    def build_task_steps(self) -> Iterable[TaskStep]:
        yield self.initialize
        selected = set(self.input_params.datasets.split(","))
        if "static" in selected:
            yield self.download_static
        if "stk_limit" in selected:
            yield self.download_stk_limits
        if "daily" in selected:
            yield self.download_daily
        if "adj_factor" in selected:
            yield self.download_adj_factors
        if "index_weight" in selected:
            yield self.download_hs300_weights
        yield self.sort_output_files

    def initialize(self) -> None:
        """Validate the requested range and initialize download state."""
        end = min(self._parse_date(self.input_params.end_date) or date.today(), date.today())
        start = self._parse_date(self.input_params.start_date)
        if start is None and self.input_params.days_back <= 0:
            raise ValueError("days_back 必须大于 0")
        start = start or end - timedelta(days=self.input_params.days_back - 1)
        if start > end:
            raise ValueError("start_date 不能晚于 end_date")
        if self.input_params.timeout <= 0:
            raise ValueError("timeout 必须大于 0")

        days = tuple(start + timedelta(days=offset) for offset in range((end - start).days + 1))
        months = tuple(self._month_bounds(day) for day in days if day.day == 1 or day == start)
        self.context.update(
            client=TushareClient(timeout=self.input_params.timeout, logger=self.logger),
            root=self.workspace_path / "tushare",
            days=days,
            months=months,
            start_date=f"{start:%Y%m%d}",
            end_date=f"{end:%Y%m%d}",
            files=[],
            rows=dict.fromkeys(DATASETS, 0),
        )
        self.logger.info(
            f"Tushare download initialized start_date={start:%Y%m%d} "
            f"end_date={end:%Y%m%d} days={len(days)} months={len(months)} "
            f"output_dir={self.context['root']}",
        )

    def download_static(self) -> None:
        """Download A-share identity, name history and trading calendar snapshots."""
        frames = [self._query("stock_basic", paginated=True, list_status=status) for status in STOCK_LIST_STATUSES]
        stock_basic = pd.concat(frames, ignore_index=True).drop_duplicates()
        self._save_static("stock_basic", stock_basic)
        for api_name in STATIC_DATASETS[1:]:
            self._save_static(api_name, self._query(api_name, paginated=True))

    def download_stk_limits(self) -> None:
        """Download official daily upper and lower price limits."""
        self._download_days("stk_limit")

    def download_daily(self) -> None:
        """Download unadjusted daily stock quotes independently."""
        self._download_days("daily")

    def download_adj_factors(self) -> None:
        """Download adjustment factors independently from daily quotes."""
        self._download_days("adj_factor")

    def download_hs300_weights(self) -> None:
        """Download HS300 weights for every month in the configured range."""
        months = self.context["months"]
        self.logger.info(f"Downloading HS300 weights month_ranges={len(months)}")
        for completed, (start, end) in enumerate(months, start=1):
            self.download_hs300_weight(start, end)
            self._report_batch_progress(completed, len(months))
        self.logger.info(f"HS300 weight download completed rows={self.context['rows']['index_weight']}")

    def sort_output_files(self) -> None:
        """Order artifacts by trading date, then by declared dataset order."""
        dataset_order = {name: index for index, name in enumerate(DATASETS)}
        self.context["files"].sort(
            key=lambda value: (
                os.path.basename(os.path.dirname(value)),
                dataset_order.get(os.path.splitext(os.path.basename(value))[0], len(dataset_order)),
                value,
            ),
        )
        self.logger.info(f"Output files sorted files={len(self.context['files'])}")

    def download_market_day(self, day: date) -> None:
        """Backward-compatible helper that downloads both legacy market datasets."""
        trade_date = f"{day:%Y%m%d}"
        daily = self._query("daily", trade_date=trade_date)
        self._save("daily", daily, day)
        self._save("adj_factor", self._query("adj_factor", trade_date=trade_date), day)

    def download_hs300_weight(self, start: date, end: date) -> None:
        """Download one date range of HS300 constituent weights."""
        frame = self._query(
            "index_weight",
            index_code=HS300,
            start_date=f"{start:%Y%m%d}",
            end_date=f"{end:%Y%m%d}",
        )
        if frame.empty:
            self.logger.info(f"No HS300 weights start_date={start:%Y%m%d} end_date={end:%Y%m%d}")
            return
        for trade_date, group in frame.groupby("trade_date", sort=True):
            self._save("index_weight", group, self._parse_date(trade_date))

    def _download_days(self, api_name: str) -> None:
        days = self.context["days"]
        self.logger.info(f"Downloading dataset={api_name} days={len(days)}")
        for completed, day in enumerate(days, start=1):
            trade_date = f"{day:%Y%m%d}"
            self._save(api_name, self._query(api_name, trade_date=trade_date), day)
            self._report_batch_progress(completed, len(days))
        self.logger.info(f"Dataset download completed dataset={api_name} rows={self.context['rows'][api_name]}")

    def _query(self, api_name: str, *, paginated: bool = False, **params: Any) -> pd.DataFrame:
        fields = ",".join(DATASETS[api_name])
        self.logger.info(f"Tushare API query api={api_name} params={params}")
        query = self.context["client"].query_has_more if paginated else self.context["client"].query
        frame = query(api_name, fields=fields, **params)
        missing = set(DATASETS[api_name]).difference(frame.columns)
        if not frame.empty and missing:
            raise RuntimeError(f"{api_name} 缺少字段: {sorted(missing)}")
        self.logger.info(f"Tushare API response api={api_name} rows={len(frame)}")
        return frame

    def _save_static(self, api_name: str, frame: pd.DataFrame) -> None:
        if frame.empty:
            return
        sort_columns = [column for column in DATASETS[api_name] if column in frame.columns]
        frame = (
            frame.loc[:, DATASETS[api_name]]
            .drop_duplicates(ignore_index=True)
            .sort_values(sort_columns, kind="stable", ignore_index=True)
        )
        path = self.context["root"] / f"{api_name}.parquet"
        self._write_frame(api_name, frame, path)

    def _save(self, api_name: str, frame: pd.DataFrame, day: date) -> None:
        if frame.empty:
            return
        sort_columns = [column for column in DATASETS[api_name] if column in frame.columns]
        frame = frame.loc[:, DATASETS[api_name]].sort_values(sort_columns, kind="stable", ignore_index=True)
        path = self.context["root"] / f"{day:%Y}" / f"{day:%Y%m%d}" / f"{api_name}.parquet"
        self._write_frame(api_name, frame, path)

    def _write_frame(self, api_name: str, frame: pd.DataFrame, path: Path) -> None:
        """Atomically persist one normalized dataset and record its artifact metadata."""
        atomic_write(
            path,
            lambda temporary: frame.to_parquet(
                temporary,
                index=False,
                compression="zstd",
                compression_level=6,
            ),
        )
        self.context["files"].append(str(path))
        self.context["rows"][api_name] += len(frame)
        self.logger.info(f"Dataset saved dataset={api_name} rows={len(frame)} path={path}")

    def _report_batch_progress(self, completed: int, total: int) -> None:
        if completed % 100 == 0 and completed < total:
            self.report_progress(completed / total * 100)

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
