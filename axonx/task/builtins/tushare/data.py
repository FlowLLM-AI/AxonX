"""Tushare dataset fields and deterministic, atomic Parquet storage."""

from datetime import date
from pathlib import Path

import pandas as pd

from ...storage.files import atomic_write

HS300 = "000300.SH"
DOWNLOAD_GROUPS = ("static", "stk_limit", "daily", "adj_factor", "index_weight")
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


class TushareDatasetStore:
    """Write selected datasets and track only successfully persisted files and rows."""

    def __init__(self, root: Path):
        self.root = root
        self.files: list[str] = []
        self.rows: dict[str, int] = dict.fromkeys(DATASETS, 0)

    def save(self, name: str, frame: pd.DataFrame, day: date | None = None) -> None:
        """Normalize columns and sorting; static snapshots also remove duplicate rows."""
        if frame.empty:
            return
        if day is None and name not in STATIC_DATASETS:
            raise ValueError(f"{name} requires a partition date")
        columns = list(DATASETS[name])
        frame = frame.loc[:, columns]
        if day is None:
            frame = frame.drop_duplicates(ignore_index=True)
        frame = frame.sort_values(columns, kind="stable", ignore_index=True)
        directory = self.root if day is None else self.root / f"{day:%Y}" / f"{day:%Y%m%d}"
        path = directory / f"{name}.parquet"
        atomic_write(
            path,
            lambda temporary: frame.to_parquet(temporary, index=False, compression="zstd", compression_level=6),
        )
        self.files.append(str(path))
        self.rows[name] += len(frame)

    def sort_files(self) -> None:
        """Order files by trading date and declared dataset order, then path."""
        order = {name: index for index, name in enumerate(DATASETS)}
        self.files.sort(key=lambda value: (Path(value).parent.name, order[Path(value).stem], value))
