"""Shared accounting and cutoff regression tests, without external data."""

import polars as pl
import pytest

from axonx.enums import TaskState
from axonx.task.builtins.stock.backtest import BaseStockBacktestTask
from axonx.task.builtins.stock.data import fixed_labels, transform_labels
from axonx.task.builtins.stock.engine import BacktestConfig, run_backtest
from axonx.task.runtime.runner import TaskRunner
from axonx.task.storage import read_metadata


def inputs():
    calendar = pl.DataFrame({"trade_date": ["20260105", "20260106", "20260107", "20260108"]})
    signals = pl.DataFrame(
        {
            "trade_date": ["20260105", "20260106"],
            "trade_time": ["1445"] * 2,
            "ts_code": ["A", "B"],
            "name": ["A", "B"],
            "pred": [2.0, 3.0],
            "is_model_candidate": [True] * 2,
            "is_buyable_at_signal": [True] * 2,
            "signal_price": [10.0, 20.0],
            "signal_adjustment_factor": [1.0] * 2,
        }
    )
    market = pl.DataFrame(
        {
            "trade_date": [
                "20260105",
                "20260106",
                "20260107",
                "20260108",
                "20260106",
                "20260107",
                "20260108",
            ],
            "trade_time": ["1445"] * 7,
            "ts_code": ["A"] * 4 + ["B"] * 3,
            "price": [10.0, None, 11.0, 12.0, 20.0, 22.0, 24.0],
            "adjustment_factor": [1.0] * 7,
            "can_buy": [True, False, True, True, True, True, True],
            "can_sell": [True, False, True, True, True, True, True],
            "market_status": [
                "quoted",
                "suspended",
                "quoted",
                "quoted",
                "quoted",
                "quoted",
                "quoted",
            ],
        }
    )
    return signals, market, calendar


def test_suspension_invalidates_fixed_label_without_searching_to_resume():
    signals, market, calendar = inputs()
    labels = fixed_labels(signals, market, calendar)
    row = labels.filter(pl.col("ts_code") == "A").row(0, named=True)
    assert row["label_target_date"] == "20260106"
    assert row["label_return"] is None and not row["label_valid"]
    assert row["label_status"] == "suspended"
    assert "label_return_rank" not in labels.columns


def test_cutoff_excluded_return_cannot_influence_rank_or_csz():
    data = pl.DataFrame(
        {
            "trade_date": ["20260105"] * 3,
            "trade_time": ["1445"] * 3,
            "label_return": [0.01, 0.02, -0.9],
            "label_valid": [True] * 3,
            "train": [True, True, False],
        }
    )
    left = transform_labels(data, reference=pl.col("train"), winsorize_tail=0.0)
    right = transform_labels(
        data.with_columns(pl.Series("label_return", [0.01, 0.02, 0.9])),
        reference=pl.col("train"),
        winsorize_tail=0.0,
    )
    assert left["label_return_rank"].to_list() == [0.0, 1.0, None]
    assert left.select("label_return_rank", "label_return_csz").equals(
        right.select("label_return_rank", "label_return_csz")
    )


def test_locked_capital_mark_to_market_and_delayed_exit():
    signals, market, calendar = inputs()
    result = run_backtest(
        signals,
        market,
        calendar,
        fixed_labels(signals, market, calendar),
        BacktestConfig(top_ns=(1,), buy_cost_rate=0, sell_cost_rate=0),
        as_of_date="20260108",
    )
    daily = result.frames["daily"]
    assert result.status == "done"
    assert daily["top1_net_value"].to_list() == pytest.approx([1.0, 1.0, 1.1, 1.1])
    assert result.frames["trades"]["exit_date"].to_list() == ["20260107"]
    assert result.frames["trades"]["exit_delayed"].to_list() == [True]
    assert result.frames["orders"].filter((pl.col("ts_code") == "B") & (pl.col("side") == "buy"))[
        "status"
    ].to_list() == ["unfilled"]
    assert daily["trade_date"].to_list() == calendar["trade_date"].to_list()


class ExitOutsideTopN:
    """Minimal membership policy for testing the engine's signal-day boundary."""

    def replacement_limit(self, n):
        return n

    def should_exit(self, *, rank, age, n):
        return age >= 1 and (rank is None or rank > n)


@pytest.mark.parametrize("last_day_signals", ["absent", "member", "no_candidates"])
def test_policy_only_exits_on_signal_days(last_day_signals):
    signals, market, calendar = inputs()
    signals = signals.filter(pl.col("ts_code") == "A")
    if last_day_signals != "absent":
        signals = pl.concat(
            [
                signals,
                signals.with_columns(
                    pl.lit("20260107").alias("trade_date"),
                    pl.lit(last_day_signals == "member").alias("is_buyable_at_signal"),
                ),
            ]
        )
    market = market.with_columns(
        pl.col("price").fill_null(10.0),
        pl.lit(True).alias("can_sell"),
        pl.lit("quoted").alias("market_status"),
    )
    result = run_backtest(
        signals,
        market,
        calendar,
        None,
        BacktestConfig(top_ns=(1,), holding_days=None, buy_cost_rate=0, sell_cost_rate=0),
        as_of_date="20260108",
        policy=ExitOutsideTopN(),
    )
    assert result.frames["orders"].filter(pl.col("trade_date") == "20260106").is_empty()
    assert result.frames["trades"]["exit_date"].to_list() == (
        ["20260107"] if last_day_signals == "no_candidates" else []
    )
    assert result.frames["daily"]["top1_net_value"].to_list() == pytest.approx(
        [1.0, 1.0, 1.1, 1.1 if last_day_signals == "no_candidates" else 1.2]
    )


@pytest.mark.parametrize("absent", [False, True])
@pytest.mark.parametrize("side", ["buy", "sell"])
def test_missing_market_can_be_assumed_suspended_without_changing_accounting(absent, side):
    signals, market, calendar = inputs()
    day = "20260105" if side == "buy" else "20260106"
    target = (pl.col("ts_code") == "A") & (pl.col("trade_date") == day)
    suspended = market.with_columns(
        pl.when(target).then(pl.lit("suspended")).otherwise(pl.col("market_status")).alias("market_status")
    )
    missing = (
        market.filter(~target)
        if absent
        else market.with_columns(
            pl.when(target).then(pl.lit("missing_data")).otherwise(pl.col("market_status")).alias("market_status")
        )
    )
    expected = run_backtest(signals, suspended, calendar, None, BacktestConfig(top_ns=(1,)), as_of_date="20260108")
    actual = run_backtest(
        signals,
        missing,
        calendar,
        None,
        BacktestConfig(top_ns=(1,), missing_market_as_suspension=True),
        as_of_date="20260108",
    )
    assert actual.status == "done"
    for name in ("daily", "orders", "positions", "trades"):
        assert actual.frames[name].equals(expected.frames[name])
    blocked = actual.frames["orders"].filter((pl.col("trade_date") == day) & (pl.col("ts_code") == "A"))
    assert blocked["reason"].to_list() == ["suspended"]
    assert blocked["fee"].to_list() == [0.0]


def test_missing_data_is_incomplete_not_confirmed_suspension():
    signals, market, calendar = inputs()
    market = market.with_columns(
        pl.when(pl.col("market_status") == "suspended")
        .then(pl.lit("missing_data"))
        .otherwise(pl.col("market_status"))
        .alias("market_status")
    )
    result = run_backtest(
        signals,
        market,
        calendar,
        None,
        BacktestConfig(top_ns=(1,), buy_cost_rate=0, sell_cost_rate=0),
        as_of_date="20260106",
    )
    assert result.status == "incomplete_market_data"
    assert result.frames["positions"].height == 2
    assert result.frames["trades"].is_empty()


@pytest.mark.parametrize("assume_suspended", [False, True])
def test_task_persists_missing_market_assumption_and_applies_it(tmp_path, assume_suspended):
    signals, market, calendar = inputs()
    market = market.with_columns(
        pl.when(pl.col("market_status") == "suspended")
        .then(pl.lit("missing_data"))
        .otherwise(pl.col("market_status"))
        .alias("market_status")
    )
    labels = fixed_labels(signals, market, calendar)
    paths = {}
    for name, frame in (("input", signals), ("market", market), ("calendar", calendar), ("labels", labels)):
        paths[name + "_file"] = tmp_path / (name + ".parquet")
        frame.write_parquet(paths[name + "_file"])
    task = BaseStockBacktestTask(
        {**paths, "top_ns": [1], "as_of_date": "20260108", "missing_market_as_suspension": assume_suspended},
        workspace_path=tmp_path / "workspace",
        reg_name="backtest",
    )
    status = TaskRunner().run(task)
    assert status.state == TaskState.SUCCEEDED, status.error
    metadata = read_metadata(task.metadata_path)
    assert metadata["input_params"]["missing_market_as_suspension"] is assume_suspended
    result = metadata["output_params"]
    assert result["protocol"]["settings"]["missing_market_as_suspension"] is assume_suspended
    assert result["universes"]["all"]["evaluation_status"] == ("done" if assume_suspended else "incomplete_market_data")
    assert ("assumed suspended" in result["protocol"]["valuation"]) is assume_suspended
    orders = pl.read_parquet(
        task.task_dir / result["artifacts"][result["universes"]["all"]["artifacts"]["orders"]]["path"]
    )
    blocked = orders.filter((pl.col("ts_code") == "A") & (pl.col("status") == "unfilled"))
    assert blocked["reason"].to_list() == ["suspended" if assume_suspended else "missing_data"]
    assert pl.read_parquet(paths["market_file"]).equals(market)
    assert pl.read_parquet(paths["labels_file"]).equals(labels)


def test_every_executed_side_pays_cost_and_future_quotes_cannot_change_prefix():
    signals, market, calendar = inputs()
    config = BacktestConfig(top_ns=(1,), buy_cost_rate=0.01, sell_cost_rate=0.01)
    full = run_backtest(signals, market, calendar, None, config, as_of_date="20260108")
    short = run_backtest(signals, market, calendar, None, config, as_of_date="20260106")
    assert (
        full.frames["daily"]
        .select("trade_date", "top1_net_value")
        .head(2)
        .equals(short.frames["daily"].select("trade_date", "top1_net_value"))
    )
    assert full.frames["orders"].filter(pl.col("status") == "filled")["fee"].sum() > 0.01
    assert full.frames["daily"]["top1_net_value"][-1] == pytest.approx(1.1 / 1.01 * 0.99)


def test_confirmed_suspension_with_stale_entry_price_is_not_a_training_label():
    from axonx.task.builtins.stock.data import apply_market_status

    signals, market, calendar = inputs()
    status = pl.DataFrame(
        {"trade_date": ["20260106"], "trade_time": ["1445"], "ts_code": ["B"], "market_status": ["suspended"]}
    )
    market = apply_market_status(market, status)
    labels = fixed_labels(signals, market, calendar)
    row = labels.filter(pl.col("ts_code") == "B").row(0, named=True)
    assert not row["label_valid"] and row["label_return"] is None
    assert row["label_status"] == "suspended"


def test_adjusted_units_preserve_value_across_split():
    signals, market, calendar = inputs()
    market = market.with_columns(
        pl.when((pl.col("ts_code") == "A") & (pl.col("trade_date") >= "20260107"))
        .then(pl.col("price") / 2)
        .otherwise(pl.col("price"))
        .alias("price"),
        pl.when((pl.col("ts_code") == "A") & (pl.col("trade_date") >= "20260107"))
        .then(2.0)
        .otherwise(pl.col("adjustment_factor"))
        .alias("adjustment_factor"),
    )
    result = run_backtest(
        signals,
        market,
        calendar,
        None,
        BacktestConfig(top_ns=(1,), buy_cost_rate=0, sell_cost_rate=0),
        as_of_date="20260108",
    )
    assert result.frames["daily"]["top1_net_value"].to_list() == pytest.approx([1.0, 1.0, 1.1, 1.1])
    assert result.frames["trades"]["realized_return"].to_list() == pytest.approx([0.1])


@pytest.mark.parametrize("bad_date", ["20260105x", "20260230", "2026015", None, "20260105"])
def test_invalid_calendar_is_rejected_by_labels_and_backtest(bad_date):
    signals, market, calendar = inputs()
    calendar = pl.concat([calendar, pl.DataFrame({"trade_date": [bad_date]}, schema={"trade_date": pl.String})])
    with pytest.raises(ValueError):
        fixed_labels(signals, market, calendar)
    with pytest.raises(ValueError):
        run_backtest(signals, market, calendar, None, BacktestConfig(top_ns=(1,)), as_of_date="20260108")


def test_index_diagnostics_ignore_outside_scores_and_returns():
    signals, market, calendar = inputs()
    first = signals.head(1).with_columns(pl.lit(0.5).alias("index_weight_test"))
    signals = pl.concat(
        [
            first,
            first.with_columns(pl.lit("D").alias("ts_code"), pl.lit(1.0).alias("pred")),
            first.with_columns(
                pl.lit("C").alias("ts_code"), pl.lit(10.0).alias("pred"), pl.lit(0.0).alias("index_weight_test")
            ),
        ]
    )
    labels = pl.DataFrame(
        {
            "trade_date": ["20260105"] * 3,
            "trade_time": ["1445"] * 3,
            "ts_code": ["A", "D", "C"],
            "label_target_date": ["20260106"] * 3,
            "label_valid": [True] * 3,
            "label_return": [0.1, 0.05, 0.2],
        }
    )
    config = BacktestConfig(top_ns=(1,))
    universe_keys = signals.filter(pl.col("index_weight_test") > 0).select("trade_date", "trade_time", "ts_code")
    before = run_backtest(signals, market, calendar, labels, config, as_of_date="20260108", universe_keys=universe_keys)
    after = run_backtest(
        signals.with_columns(pl.when(pl.col("ts_code") == "C").then(-10.0).otherwise(pl.col("pred")).alias("pred")),
        market,
        calendar,
        labels.with_columns(
            pl.when(pl.col("ts_code") == "C").then(-0.9).otherwise(pl.col("label_return")).alias("label_return")
        ),
        config,
        as_of_date="20260108",
        universe_keys=universe_keys,
    )
    merged = before.frames["signals"]
    assert merged["ts_code"].to_list() == ["A", "D", "C"]
    assert merged.filter(pl.col("is_backtest_candidate"))["ts_code"].to_list() == ["A", "D"]
    excluded = merged.filter(~pl.col("is_backtest_candidate"))
    assert excluded["target_rank"].to_list() == [None]
    assert excluded["label_return"].to_list() == [None]
    columns = ["ic", "rank_ic", "top1_ndcg"]
    assert before.frames["daily"].select(columns).equals(after.frames["daily"].select(columns))
    assert before.frames["daily"]["top1_ndcg"][0] == pytest.approx(1.0)


def test_unfilled_top_target_is_not_replaced():
    signals, market, calendar = inputs()
    first = signals.head(1)
    signals = pl.concat([first, first.with_columns(pl.lit("B").alias("ts_code"), pl.lit(1.0).alias("pred"))])
    first_quote = market.filter((pl.col("trade_date") == "20260105") & (pl.col("ts_code") == "A"))
    market = pl.concat(
        [
            market.with_columns(
                pl.when(pl.col("ts_code") == "A").then(False).otherwise(pl.col("can_buy")).alias("can_buy")
            ),
            first_quote.with_columns(pl.lit("B").alias("ts_code")),
        ]
    )
    result = run_backtest(
        signals,
        market,
        calendar,
        None,
        BacktestConfig(top_ns=(1,), buy_cost_rate=0, sell_cost_rate=0),
        as_of_date="20260108",
    )
    assert result.frames["positions"].is_empty()
    assert result.frames["trades"].is_empty()
    assert result.frames["orders"]["ts_code"].to_list() == ["A"]
    assert result.frames["daily"]["top1_net_value"].to_list() == [1.0] * 4


def test_empty_labels_keep_portfolio_and_nullable_diagnostics():
    signals, market, calendar = inputs()
    labels = fixed_labels(signals, market, calendar).clear()
    config = BacktestConfig(top_ns=(1, 3), buy_cost_rate=0, sell_cost_rate=0)
    result = run_backtest(signals, market, calendar, labels, config, as_of_date="20260108")
    without = run_backtest(signals, market, calendar, None, config, as_of_date="20260108")
    assert (
        result.frames["daily"]
        .select("top1_net_value", "top3_net_value")
        .equals(without.frames["daily"].select("top1_net_value", "top3_net_value"))
    )
    assert result.frames["daily"]["ic"].null_count() == 4
    assert result.frames["daily"]["top3_ndcg"].null_count() == 4
    assert result.frames["signals"]["label_return"].null_count() == signals.height


@pytest.mark.parametrize("bad_time", ["2400", "1260", "945", "15:00", None])
def test_invalid_signal_time_is_rejected(bad_time):
    signals, market, calendar = inputs()
    signals = signals.with_columns(pl.lit(bad_time, dtype=pl.String).alias("trade_time"))
    with pytest.raises(ValueError):
        fixed_labels(signals, market, calendar)
    with pytest.raises(ValueError):
        run_backtest(signals, market, calendar, None, BacktestConfig(top_ns=(1,)), as_of_date="20260108")


@pytest.mark.parametrize("buy,sell", [(0.0005, 0.0015), (0.0, 0.0015)])
def test_asymmetric_fees_preserve_cash_and_charge_only_executed_sides(buy, sell):
    signals, market, calendar = inputs()
    config = BacktestConfig(top_ns=(1,), buy_cost_rate=buy, sell_cost_rate=sell)
    result = run_backtest(signals, market, calendar, None, config, as_of_date="20260108")
    rate = buy
    orders = result.frames["orders"]
    for row in orders.filter(pl.col("status") == "filled").iter_rows(named=True):
        expected = rate if row["side"] == "buy" else sell
        assert row["fee"] == pytest.approx(row["notional"] * expected)
    assert orders.filter(pl.col("status") != "filled")["fee"].sum() == 0
    assert result.frames["daily"]["top1_net_value"][-1] == pytest.approx(1.1 / (1 + rate) * (1 - sell))


@pytest.mark.parametrize("buy,sell", [(-0.01, 0.002), (0.002, 1.0)])
def test_invalid_side_cost_is_rejected(buy, sell):
    signals, market, calendar = inputs()
    with pytest.raises(ValueError, match="buy_cost_rate and sell_cost_rate"):
        run_backtest(
            signals,
            market,
            calendar,
            None,
            BacktestConfig(top_ns=(1,), buy_cost_rate=buy, sell_cost_rate=sell),
            as_of_date="20260108",
        )


def test_backtest_schema_has_only_explicit_side_fees():
    from axonx.task.builtins.stock import StockBacktestInput

    assert "transaction_cost_rate" not in StockBacktestInput.model_fields
    defaults = StockBacktestInput()
    assert defaults.buy_cost_rate == 0.0005
    assert defaults.sell_cost_rate == 0.0015
    with pytest.raises(ValueError):
        StockBacktestInput(transaction_cost_rate=0.001)
    with pytest.raises(ValueError):
        StockBacktestInput(buy_cost_rate=None)


class RecordingEvents:
    successors = {"C"}

    def __init__(self, *, lock_first=False, pending_cash=0.0, blocked_codes=()):
        self.lock_first = lock_first
        self.pending_cash = pending_cash
        self.blocked_codes = set(blocked_codes)
        self.runs = {}
        self.top_n = None

    def reset(self, top_n):
        self.top_n = top_n
        self.runs[top_n] = []

    def apply(self, date, slot, book, cash, quotes):
        self.runs[self.top_n].append((date, slot, {code: dict(p) for code, p in book.items()}, set(quotes)))
        if self.lock_first and self.top_n == 1 and "A" in book:
            quotes["A"]["can_sell"] = False
        return cash

    def blocked(self, code):
        return code in self.blocked_codes


def test_top_ns_replay_matches_separate_runs():
    signals, market, calendar = inputs()
    config = BacktestConfig(top_ns=(2, 1))
    combined = run_backtest(signals, market, calendar, None, config, as_of_date="20260108")
    for n in config.top_ns:
        separate = run_backtest(signals, market, calendar, None, BacktestConfig(top_ns=(n,)), as_of_date="20260108")
        columns = ["trade_date", *[c for c in separate.frames["daily"].columns if c.startswith(f"top{n}_")]]
        assert combined.frames["daily"].select(columns).equals(separate.frames["daily"].select(columns))
        for name in ("orders", "positions", "trades"):
            assert combined.frames[name].filter(pl.col("top_n") == n).equals(separate.frames[name])


def test_noop_events_preserve_execution_and_load_successor_quotes():
    signals, market, calendar = inputs()
    market = pl.concat(
        [
            market,
            market.filter(pl.col("ts_code") == "A").with_columns(pl.lit("C").alias("ts_code")),
        ]
    )
    events = RecordingEvents()
    config = BacktestConfig(top_ns=(1, 2))
    original = run_backtest(signals, market, calendar, None, config, as_of_date="20260108")
    result = run_backtest(signals, market, calendar, None, config, as_of_date="20260108", events=events)
    assert result.status == original.status
    assert result.benchmark_keys == original.benchmark_keys
    for name, frame in original.frames.items():
        actual = result.frames[name]
        if name == "daily":
            assert actual.select("top1_pending_cash", "top2_pending_cash").to_numpy().sum() == 0
            actual = actual.drop("top1_pending_cash", "top2_pending_cash")
        assert frame.equals(actual), name
    for calls in events.runs.values():
        assert len(calls) == calendar.height
        date, slot, book, quotes = calls[1]
        assert (date, slot) == ("20260106", "1445")
        assert "C" in quotes
        position = book["A"]
        assert position["entry_shares"] == pytest.approx(position["principal"] / position["entry_price"])
        assert position["entry_factor"] == position["last_factor"] == 1


def test_event_quote_mutations_do_not_affect_the_next_top_n_replay():
    signals, market, calendar = inputs()
    market = market.with_columns(
        pl.col("price").fill_null(10),
        pl.lit("quoted").alias("market_status"),
        pl.lit(True).alias("can_buy"),
        pl.lit(True).alias("can_sell"),
    )
    result = run_backtest(
        signals,
        market,
        calendar,
        None,
        BacktestConfig(top_ns=(1, 2)),
        as_of_date="20260108",
        events=RecordingEvents(lock_first=True),
    )
    orders = result.frames["orders"].filter((pl.col("trade_date") == "20260106") & (pl.col("side") == "sell"))
    assert orders.select("top_n", "status").rows() == [(1, "unfilled"), (2, "filled")]
    assert market["can_sell"].all()


@pytest.mark.parametrize("pending_cash", [-0.1, float("nan"), float("inf")])
def test_event_receivables_must_be_finite_and_nonnegative(pending_cash):
    signals, market, calendar = inputs()
    with pytest.raises(ValueError, match="Invalid pending cash"):
        run_backtest(
            signals,
            market,
            calendar,
            None,
            BacktestConfig(top_ns=(1,)),
            as_of_date="20260108",
            events=RecordingEvents(pending_cash=pending_cash),
        )


def test_event_blocked_candidate_without_quotes_does_not_mark_replay_incomplete():
    signals, market, calendar = inputs()
    market = market.filter(pl.col("ts_code") != "A")
    result = run_backtest(
        signals,
        market,
        calendar,
        None,
        BacktestConfig(top_ns=(1,)),
        as_of_date="20260108",
        events=RecordingEvents(blocked_codes={"A"}),
    )
    assert result.status == "done"
    order = result.frames["orders"].row(0, named=True)
    assert (order["ts_code"], order["status"], order["reason"]) == (
        "A",
        "unfilled",
        "security_event",
    )


@pytest.mark.parametrize("invalid", ["duplicate", "foreign"])
def test_universe_keys_are_a_unique_subset_of_signals(invalid):
    signals, market, calendar = inputs()
    keys = signals.select("trade_date", "trade_time", "ts_code")
    keys = (
        pl.concat([keys, keys.head(1)])
        if invalid == "duplicate"
        else keys.with_columns(pl.lit("UNKNOWN").alias("ts_code"))
    )
    with pytest.raises(ValueError, match="[Dd]uplicate|[Uu]niverse"):
        run_backtest(
            signals, market, calendar, None, BacktestConfig(top_ns=(1,)), as_of_date="20260108", universe_keys=keys
        )


def test_empty_universe_keeps_cash_and_does_not_erase_signal_dates():
    signals, market, calendar = inputs()
    keys = signals.select("trade_date", "trade_time", "ts_code").head(0)
    result = run_backtest(
        signals, market, calendar, None, BacktestConfig(top_ns=(1,)), as_of_date="20260108", universe_keys=keys
    )
    assert result.frames["daily"]["top1_net_value"].to_list() == [1.0] * 4
    assert result.frames["daily"]["candidate_count"].to_list() == [0] * 4
    assert result.frames["orders"].is_empty()
    assert not result.frames["signals"]["is_backtest_candidate"].any()


def test_backtest_contract_requires_reports_and_resolves_every_artifact():
    from axonx.enums import TaskType
    from axonx.task.contracts import BaseBacktestOutputParams
    from axonx.task.protocol import task_protocol

    report = {
        "label": "All",
        "parameters": {},
        "dimensions": {"top_ns": [1], "holding_detail_top_n": 30, "benchmarks": []},
        "date_range": {},
        "days": 0,
        "evaluation_status": "done",
        "artifacts": {"daily": "all_daily", "summary": "all_summary"},
    }
    shared = {
        "protocol": task_protocol(TaskType.BACKTEST),
        "artifacts": {
            "all_daily": {"path": "daily.parquet", "size": 1, "sha256": "0" * 64},
            "all_summary": {"path": "summary.parquet", "size": 1, "sha256": "0" * 64},
        },
    }
    assert BaseBacktestOutputParams(default_universe="all", universes={"all": report}, **shared)
    with pytest.raises(ValueError, match="default_universe"):
        BaseBacktestOutputParams(default_universe="missing", universes={"all": report}, **shared)
    with pytest.raises(ValueError, match="unregistered"):
        BaseBacktestOutputParams(
            default_universe="all",
            universes={"all": {**report, "artifacts": {"daily": "other", "summary": "all_summary"}}},
            **shared,
        )
    with pytest.raises(ValueError):
        BaseBacktestOutputParams(dimensions=report["dimensions"], days=0, date_range={}, **shared)


def test_relative_drawdown_subtracts_daily_returns_and_resets_each_period():
    from axonx.task.builtins.stock.reporting import summarize

    daily = pl.DataFrame(
        {
            "trade_date": ["20251230", "20251231", "20260105", "20260106"],
            "ic": [0.0] * 4,
            "rank_ic": [0.0] * 4,
            "benchmark_universe_return": [0.2, 0.0, 0.0, 0.0],
            "benchmark_equal_return": [0.1, 0.1, -0.1, 0.05],
            "benchmark_partial_return": [None, 0.2, float("nan"), 0.0],
            "benchmark_missing_return": [None] * 4,
            **{
                f"top{n}_{key}": values
                for n in (1, 3)
                for key, values in {
                    "net_return": [0.1, 0.1, -0.1, 0.05],
                    "gross_return": [0.3, 0.3, 0.1, 0.25],
                    "turnover": [0.0] * 4,
                    "delayed_exits": [0] * 4,
                    "unsettled_positions": [0] * 4,
                }.items()
            },
        },
        schema_overrides={"benchmark_missing_return": pl.Float64},
    )
    summary = summarize(daily.reverse(), ("universe", "equal", "partial", "missing"), 0.0, 252, (1, 3))
    overall = summary.filter(pl.col("period_type") == "overall").row(0, named=True)
    for n in (1, 3):
        # .9 * 1.1 * .9 = .891, with initial equity 1 included in the peak.
        assert overall[f"top{n}_net_relative_max_drawdown_universe"] == pytest.approx(-0.109)
        assert overall[f"top{n}_net_relative_max_drawdown_equal"] == pytest.approx(0.0)
        assert overall[f"top{n}_net_relative_max_drawdown_partial"] == pytest.approx(-0.1)
        assert overall[f"top{n}_net_relative_max_drawdown_missing"] is None
        assert overall[f"top{n}_net_max_drawdown"] == pytest.approx(-0.1)
    for period_type in ("year", "quarter", "month"):
        rows = summary.filter(pl.col("period_type") == period_type)
        assert rows.height == 2
        assert rows["top1_net_relative_max_drawdown_universe"].to_list() == pytest.approx([-0.1, -0.1])
    no_benchmarks = summarize(daily, (), 0.0, 252, (1,))
    assert not any("relative_max_drawdown" in c for c in no_benchmarks.columns)
