import json
from pathlib import Path

import polars as pl
import pytest

from axonx.task.alpha158 import Alpha158Config, Alpha158Task
from axonx.task.alpha158.alpha158_etl import (
    FEATURES,
    LABEL_OUTPUTS,
    MARKET_STATE_COLUMNS,
)


def _write_partition(root: Path, trade_date: str, name: str, rows: list[dict]) -> None:
    path = root / "tushare" / trade_date[:4] / trade_date / f"{name}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_parquet(path)


def _write_reference_data(root: Path, dates: list[str], codes: list[str]) -> None:
    directory = root / "tushare"
    directory.mkdir(parents=True, exist_ok=True)
    pl.DataFrame({"cal_date": dates, "is_open": [1] * len(dates)}).write_parquet(
        directory / "trade_cal.parquet",
    )
    pl.DataFrame(
        {
            "ts_code": codes,
            "name": [f"股票{index}" for index in range(len(codes))],
            "list_date": ["20200101"] * len(codes),
            "delist_date": [""] * len(codes),
        },
    ).write_parquet(directory / "stock_basic.parquet")
    pl.DataFrame(
        {
            "ts_code": codes,
            "name": ["*ST历史股票0" if index == 0 else f"历史股票{index}" for index in range(len(codes))],
            "start_date": ["20200101"] * len(codes),
            "ann_date": ["20200101"] * len(codes),
        },
    ).write_parquet(directory / "namechange.parquet")


def test_alpha158_defaults_to_data_since_2014():
    config = Alpha158Config()

    assert config.start_date == "20140101"
    assert config.end_date is None
    assert config.csz_winsorize_tail == pytest.approx(0.025)
    assert config.min_history_coverage == pytest.approx(0.8)


def test_alpha158_csz_winsorizes_configured_cross_section_tails(tmp_path):
    task = Alpha158Task({"csz_winsorize_tail": 0.25}, workspace_path=tmp_path)
    frame = pl.DataFrame(
        {
            "trade_date": ["20260105", "20260106"] * 4,
            "ts_code": [code for code in ("A", "B", "C", "D") for _ in range(2)],
            "_close": [100.0, 100.0, 100.0, 101.0, 100.0, 102.0, 100.0, 200.0],
        },
    )

    first_day = task._labels(frame).filter(pl.col("trade_date") == "20260105")

    assert first_day["label_1d"].to_list() == pytest.approx([0.0, 0.01, 0.02, 1.0])
    assert first_day["label_1d_csz"].to_list() == pytest.approx(
        [-0.622512, -0.599667, -0.508289, 1.730468],
        abs=1e-6,
    )


def test_alpha158_infers_lifecycle_for_daily_symbol_missing_from_stock_basic(
    tmp_path,
):
    dates = ["20260105", "20260106", "20260107"]
    _write_reference_data(tmp_path, dates, ["000001.SZ"])
    quotes = {
        "20260105": [("000001.SZ", 10.0), ("000999.SZ", 20.0)],
        "20260106": [("000001.SZ", 10.5)],
        "20260107": [("000001.SZ", 11.0), ("000999.SZ", 21.0)],
    }
    for trade_date, rows in quotes.items():
        _write_partition(
            tmp_path,
            trade_date,
            "daily",
            [
                {
                    "ts_code": code,
                    "trade_date": trade_date,
                    "open": close,
                    "high": close,
                    "low": close,
                    "close": close,
                    "pre_close": close,
                    "vol": 1000.0,
                    "amount": close * 100.0,
                }
                for code, close in rows
            ],
        )
        _write_partition(
            tmp_path,
            trade_date,
            "adj_factor",
            [{"ts_code": code, "trade_date": trade_date, "adj_factor": 1.0} for code, _ in rows],
        )

    task = Alpha158Task({}, workspace_path=tmp_path)
    output = task.execute()

    result = pl.read_parquet(output["output_file"])
    inferred = result.filter(pl.col("ts_code") == "000999.SZ")
    metadata = json.loads(Path(output["metadata_file"]).read_text())
    assert task.context["missing_stock_basic_symbols"] == 1
    assert metadata["market_state"]["missing_stock_basic_symbols"] == 1
    assert inferred["trade_date"].to_list() == ["20260105", "20260107"]
    assert inferred["name"].unique().to_list() == ["000999.SZ"]
    assert inferred["list_date"].unique().to_list() == ["20260105"]
    assert inferred["delist_date"].null_count() == inferred.height


def test_alpha158_builds_strict_forward_labels_and_snapshot_weights(tmp_path):
    quotes = {
        "20260105": [
            ("000001.SZ", 10.0),
            ("000002.SZ", 20.0),
            ("920001.BJ", 30.0),
        ],
        "20260107": [
            ("000001.SZ", 12.0),
            ("000002.SZ", 22.0),
            ("920001.BJ", 33.0),
        ],
    }
    _write_reference_data(
        tmp_path,
        ["20260105", "20260106", "20260107"],
        ["000001.SZ", "000002.SZ", "920001.BJ"],
    )
    previous_closes: dict[str, float] = {}
    for trade_date, stocks in quotes.items():
        _write_partition(
            tmp_path,
            trade_date,
            "daily",
            [
                {
                    "ts_code": code,
                    "trade_date": trade_date,
                    "open": close - 0.2,
                    "high": close + 0.5,
                    "low": close - 0.5,
                    "close": close,
                    "pre_close": previous_closes.get(code, close - 0.1),
                    "vol": 1000.0,
                    "amount": close * 100.0,
                }
                for code, close in stocks
            ],
        )
        _write_partition(
            tmp_path,
            trade_date,
            "adj_factor",
            [
                {"ts_code": code, "trade_date": trade_date, "adj_factor": 1.0}
                for code, _ in stocks
                if not (trade_date == "20260105" and code == "000001.SZ")
            ],
        )
        _write_partition(
            tmp_path,
            trade_date,
            "stk_limit",
            [
                {
                    "ts_code": code,
                    "trade_date": trade_date,
                    "up_limit": close * 1.1,
                    "down_limit": close * 0.9,
                }
                for code, close in stocks
                if not (trade_date == "20260105" and code == "000002.SZ")
            ],
        )
        previous_closes.update(stocks)

    _write_partition(
        tmp_path,
        "20260105",
        "index_weight",
        [
            {
                "index_code": "000300.SH",
                "con_code": "000001.SZ",
                "trade_date": "20260105",
                "weight": 60.0,
            },
            {
                "index_code": "000300.SH",
                "con_code": "000002.SZ",
                "trade_date": "20260105",
                "weight": 40.0,
            },
        ],
    )
    _write_partition(
        tmp_path,
        "20260107",
        "index_weight",
        [
            {
                "index_code": "000300.SH",
                "con_code": "000002.SZ",
                "trade_date": "20260107",
                "weight": 100.0,
            },
        ],
    )

    task = Alpha158Task({}, workspace_path=tmp_path)
    snapshots = []
    output = task.execute(emit=snapshots.append)
    result = pl.read_parquet(output["output_file"])

    assert task.context["filled_adj_factor_rows"] == 1
    assert task.context["fallback_limit_rows"] == 1
    assert task.context["missing_limit_rows"] == 0
    assert not result["ts_code"].str.ends_with(".BJ").any()

    assert [step.name for step in task.status.steps] == [
        "resolve_paths",
        "load_and_validate_market_data",
        "build_trading_panel",
        "calculate_base_features",
        "calculate_rolling_features",
        "attach_market_status",
        "calculate_labels",
        "attach_index_weights",
        "finalize_dataset",
        "calculate_statistics",
        "write_outputs",
        "write_metadata",
        "publish_output",
    ]
    rolling_progress = [
        status.steps[4].percentage
        for status in snapshots
        if len(status.steps) == 5 and status.steps[4].percentage is not None
    ]
    assert rolling_progress == [10, 23, 41, 64, 95, 100]
    statistics_progress = [
        status.steps[9].percentage
        for status in snapshots
        if len(status.steps) == 10 and status.steps[9].percentage is not None
    ]
    assert statistics_progress == sorted(statistics_progress)
    assert statistics_progress[-2:] == [95, 100]
    assert output["feature_count"] == 158
    assert Path(output["output_file"]) == tmp_path / "etl" / task.task_id / "alpha158.parquet"
    assert Path(output["statistics_file"]) == tmp_path / "etl" / task.task_id / "alpha158.csv"
    assert result.columns == [
        "trade_date",
        "ts_code",
        *MARKET_STATE_COLUMNS,
        *FEATURES,
        *LABEL_OUTPUTS,
        "index_weight_hs300",
    ]
    assert Path(output["statistics_file"]).name == "alpha158.csv"
    assert Path(output["metadata_file"]) == tmp_path / "etl" / task.task_id / "metadata.json"
    metadata = json.loads(Path(output["metadata_file"]).read_text())
    assert metadata["task_id"] == task.task_id
    assert metadata["feature_columns"] == list(FEATURES)
    assert metadata["artifacts"]["dataset"] == "alpha158.parquet"
    statistics = pl.read_csv(output["statistics_file"])
    assert statistics.height == len(FEATURES) + len(LABEL_OUTPUTS)
    assert statistics.columns == [
        "column",
        "total_count",
        "finite_count",
        "null_count",
        "nan_count",
        "inf_count",
        "finite_rate",
        "null_rate",
        "nan_rate",
        "inf_rate",
        "zero_rate",
        "min",
        "p03",
        "p50",
        "p97",
        "max",
        "mean",
        "std",
        "unique_count",
    ]
    label_2d_statistics = statistics.filter(pl.col("column") == "label_2d")
    assert label_2d_statistics["finite_count"].item() == 2
    assert label_2d_statistics["null_count"].item() == 2
    assert label_2d_statistics["nan_rate"].item() == 0
    assert label_2d_statistics["inf_rate"].item() == 0
    assert result.filter(pl.col("ts_code") == "000001.SZ")["label_1d"].to_list() == [
        None,
        None,
    ]
    assert result.filter(pl.col("ts_code") == "000001.SZ")["label_2d"].to_list() == pytest.approx(
        [0.2, None],
        nan_ok=True,
    )
    assert result.filter(pl.col("ts_code") == "000002.SZ")["label_1d"].to_list() == [
        None,
        None,
    ]
    assert result.filter(pl.col("ts_code") == "000002.SZ")["label_2d"].to_list() == pytest.approx(
        [0.1, None],
        nan_ok=True,
    )
    first_day = result.filter(pl.col("trade_date") == "20260105")
    assert first_day["label_2d_csz"].to_list() == pytest.approx([1.0, -1.0])
    assert first_day["label_2d_rank"].to_list() == pytest.approx([1.0, 0.5])
    assert first_day["label_2d_is_valid"].to_list() == [True, True]
    assert result.filter(pl.col("ts_code") == "000002.SZ")["label_1d_is_valid"].to_list() == [False, False]
    assert result["index_weight_hs300"].to_list() == pytest.approx([0.6, 0.4, 0.0, 1.0])
    assert result["name"].unique().sort().to_list() == ["*ST历史股票0", "历史股票1"]
    assert result.filter(pl.col("ts_code") == "000001.SZ")["is_st"].all()
    assert result["is_insufficient_history"].all()
    assert not result["is_buyable"].any()
    # The missing 20260106 quote remains a calendar row inside B's rolling window.
    b_last = result.filter(
        (pl.col("ts_code") == "000002.SZ") & (pl.col("trade_date") == "20260107"),
    )
    assert b_last["f_alpha158_CNTP5"].item() == pytest.approx(0.0)
