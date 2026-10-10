"""Historical empty Parquet partitions must not dictate the combined quote schema."""

import polars as pl

from axonx_qlib_a158.internal.etl_pipeline import load_index_weights, load_market_data, load_price_limits


def partitions(tmp_path, name, rows):
    populated = pl.DataFrame(rows)
    empty_path, full_path = tmp_path / f"{name}-empty.parquet", tmp_path / f"{name}-full.parquet"
    pl.DataFrame({column: [] for column in populated.columns}).write_parquet(empty_path)
    populated.write_parquet(full_path)
    no_columns_path = tmp_path / f"{name}-no-columns.parquet"
    pl.DataFrame().write_parquet(no_columns_path)
    return [no_columns_path, empty_path, full_path]


def test_empty_partitions_are_normalized_before_quote_join(tmp_path):
    prices = {name: [10] for name in ("open", "high", "low", "close", "pre_close", "vol", "amount")}
    keys = {"ts_code": ["000001.SZ"], "trade_date": ["20260105"]}
    daily = partitions(tmp_path, "daily", {**keys, **prices})
    factors = partitions(tmp_path, "factor", {**keys, "adj_factor": [1]})
    frame = load_market_data(daily, factors)
    assert frame.height == 1
    assert frame["ts_code"].to_list() == ["000001.SZ"]
    assert frame.schema["close"] == frame.schema["adj_factor"] == pl.Float64


def test_empty_limits_and_index_weight_partitions(tmp_path):
    limits = partitions(
        tmp_path,
        "limits",
        {
            "ts_code": ["000001.SZ"],
            "trade_date": ["20260105"],
            "up_limit": [11],
            "down_limit": [9],
        },
    )
    assert load_price_limits(limits)["up_limit"].to_list() == [11.0]
    weights = partitions(
        tmp_path,
        "weights",
        {
            "index_code": ["000300.SH", "other"],
            "con_code": ["000001.SZ", "000002.SZ"],
            "trade_date": ["20260105"] * 2,
            "weight": [10, 20],
        },
    )
    frame, snapshots = load_index_weights(weights)
    assert frame["index_weight_hs300"].to_list() == [0.1]
    assert snapshots["_weight_date"].to_list() == ["20260105"]


def test_empty_optional_partitions_keep_typed_outputs(tmp_path):
    empty = tmp_path / "empty.parquet"
    pl.DataFrame().write_parquet(empty)
    limits = load_price_limits([empty])
    assert limits.is_empty() and limits.schema["up_limit"] == pl.Float64
    weights, snapshots = load_index_weights([empty])
    assert weights.is_empty() and weights.schema["index_weight_hs300"] == pl.Float64
    assert snapshots.is_empty() and snapshots.schema["_weight_date"] == pl.String
