"""Input validation for prediction frames consumed by backtests."""

import polars as pl


def validate_prediction_frame(
    frame: pl.DataFrame, index_columns: tuple[str, ...]
) -> None:
    """Validate dates, returns, and benchmark weights before backtesting."""
    if frame.is_empty():
        raise ValueError("预测文件为空")
    if frame.select("trade_date", "ts_code").n_unique() != frame.height:
        raise ValueError("预测文件包含重复的 trade_date, ts_code")
    invalid_number = pl.any_horizontal(
        pl.col("pred", "actual_return").is_not_null()
        & ~pl.col("pred", "actual_return").is_finite()
    )
    invalid_label = pl.col("label_valid") & (
        pl.col("actual_return").is_null() | (pl.col("actual_return") <= -1)
    )
    if frame.filter(
        pl.col("trade_date").str.to_date("%Y%m%d", strict=False).is_null()
    ).height:
        raise ValueError("trade_date 必须是有效 YYYYMMDD")
    if frame.filter(invalid_number).height:
        raise ValueError("pred 或 actual_return 包含非有限值")
    if frame.filter(invalid_label).height:
        raise ValueError("有效 actual_return 必须非空且大于 -1")
    for column in index_columns:
        weight = pl.col(column)
        if frame.filter(
            weight.is_not_null() & (~weight.is_finite() | (weight < 0))
        ).height:
            raise ValueError(f"{column} 必须是非负有限小数权重")
        if frame.group_by("trade_date").agg(weight.sum()).filter(weight > 1.05).height:
            raise ValueError(f"{column} 每日合计不能明显超过 1")
