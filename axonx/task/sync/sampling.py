"""Bounded, whole-day Parquet sampling for read-only display replicas."""

import io
from pathlib import Path

import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq

from .errors import ReplicaBudgetError


def trade_day():
    return pl.col("trade_date").cast(pl.String).str.replace_all("-", "")


class _BudgetWriter(io.BufferedWriter):
    def __init__(self, path: Path, limit: int):
        super().__init__(path.open("wb", buffering=0))
        self.limit = limit

    def write(self, data):
        if self.tell() + len(data) > self.limit:
            raise ReplicaBudgetError("Encoded sample exceeds the remaining transfer budget")
        return super().write(data)


def write_sample(source: Path, target: Path, dates: list[str], limit: int) -> None:
    parquet = pq.ParquetFile(source)
    groups = []
    column = next(i for i in range(len(parquet.schema)) if parquet.schema.column(i).path == "trade_date")
    for index in range(parquet.metadata.num_row_groups):
        stats = parquet.metadata.row_group(index).column(column).statistics
        if stats is not None and stats.has_min_max:
            lower, upper = str(stats.min).replace("-", ""), str(stats.max).replace("-", "")
            if not any(lower <= day <= upper for day in dates):
                continue
        groups.append(index)
    with (
        _BudgetWriter(target, limit) as stream,
        pq.ParquetWriter(stream, parquet.schema_arrow, compression="zstd") as writer,
    ):
        pending, pending_bytes = [], 0
        for batch in parquet.iter_batches(batch_size=8192, row_groups=groups):
            frame = pl.from_arrow(batch).filter(trade_day().is_in(dates))
            if frame.height:
                table = frame.to_arrow().cast(parquet.schema_arrow)
                pending.append(table)
                pending_bytes += table.nbytes
                if pending_bytes >= 16 * 1024 * 1024:
                    writer.write_table(pa.concat_tables(pending))
                    pending, pending_bytes = [], 0
        if pending:
            writer.write_table(pa.concat_tables(pending))
