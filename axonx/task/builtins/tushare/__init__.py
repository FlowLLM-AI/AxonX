"""Tushare API access, dataset storage and download orchestration.

client: Bounded retries, pagination, request budgets and owned-session cleanup.
data: Dataset definitions, normalized Parquet persistence and successful-write accounting.
task: Download parameters, date-range selection, dataset steps and typed results.
"""

from . import client, data, task
from .client import TushareClient
from .task import (
    DownloadTushareTask,
    TushareDownloadInputParams,
    TushareDownloadOutputParams,
)

__all__ = [
    "DownloadTushareTask",
    "TushareClient",
    "TushareDownloadInputParams",
    "TushareDownloadOutputParams",
    "client",
    "data",
    "task",
]
