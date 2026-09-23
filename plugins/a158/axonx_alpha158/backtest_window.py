"""Find a safe prediction cutoff for the pipeline backtest."""

import json
import sys
from pathlib import Path

import polars as pl


def settled_end(path: Path) -> str | None:
    """Return a cutoff when top picks lack an exit price near the data tail."""
    frame = pl.scan_parquet(path).select(
        "trade_date",
        "ts_code",
        "pred",
        "is_buyable",
        "entry_is_buyable",
        "exit_is_sellable",
        "label_valid",
    )
    settled_dates = frame.filter("label_valid").select("trade_date").unique()
    candidates = (
        frame.filter(pl.col("is_buyable") & pl.col("pred").is_not_null())
        .join(settled_dates, on="trade_date", how="inner")
        .sort("trade_date", "pred", "ts_code", descending=(False, True, False))
        .with_columns(pl.col("ts_code").cum_count().over("trade_date").alias("rank"))
    )
    unsafe = (
        candidates.filter(
            (pl.col("rank") <= 30)
            & pl.col("entry_is_buyable")
            & (~pl.col("label_valid") | ~pl.col("exit_is_sellable"))
        )
        .select(pl.col("trade_date").min())
        .collect()
        .item()
    )
    if unsafe is None:
        return None

    recent = (
        frame.select("trade_date")
        .unique()
        .sort("trade_date", descending=True)
        .limit(3)
        .collect()["trade_date"]
        .to_list()
    )
    if unsafe < recent[-1]:
        raise ValueError(f"预测数据在 {unsafe} 已缺少回测退出价；请检查历史行情")
    cutoff = (
        frame.filter(pl.col("trade_date") < unsafe)
        .select(pl.col("trade_date").max())
        .collect()
        .item()
    )
    if cutoff is None:
        raise ValueError(f"预测数据从 {unsafe} 起缺少回测退出价")
    print(
        f"Backtest excludes unsettled dates from {unsafe}; prediction end: {cutoff}",
        file=sys.stderr,
    )
    return cutoff


if __name__ == "__main__":
    response = json.load(sys.stdin)
    status = response["answer"]
    if not response["success"] or status["state"] != "succeeded":
        raise SystemExit("Prediction status is not successful")
    path = Path(status["result"]["predictions_file"])
    if not path.is_file():
        raise SystemExit(f"Prediction file is not accessible: {path}")
    print(settled_end(path) or "")
