"""Standard stock backtest Task: plugins supply artifacts, not copied ledgers."""

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import polars as pl

from ...core.standard import BaseBacktestTask
from ...core.task import TaskStep
from ...models.artifacts import PredictionProtocol, task_protocol
from ...models.identity import TaskType, parse_source_tasks, task_type_from_id
from ...models.reports import (
    BacktestBenchmark,
    BacktestDimensions,
    BacktestUniverse,
    BacktestUniverseReport,
)
from ...storage.artifacts import artifact_record, read_metadata
from ...storage.files import atomic_write, file_revision
from ...storage.inputs import pin_source_artifacts
from .data import KEYS
from .engine import PortfolioPolicy, run_backtest
from .models import (
    BacktestConfig,
    PortfolioSettings,
    StockBacktestInput,
    StockBacktestOutput,
)
from .protocol import STOCK_SIGNALS_FORMAT


class BaseStockBacktestTask(BaseBacktestTask):
    input_cls = StockBacktestInput
    output_cls = StockBacktestOutput
    input_params: StockBacktestInput

    def build_task_steps(self) -> Iterable[TaskStep]:
        yield self.resolve_inputs
        yield self.calculate
        yield self.write_outputs

    def source_file(self, task_id: str, name: str) -> tuple[Path, dict[str, Any]]:
        root = self.source_task_dir(task_id)
        metadata = read_metadata(root / "metadata.json")
        (path,) = pin_source_artifacts(self, task_id, name, metadata=metadata)
        return path, metadata

    def resolve_inputs(self) -> None:
        p = self.input_params
        paths = {key: getattr(p, key + "_file") for key in ("input", "market", "calendar", "labels")}
        sources = parse_source_tasks(p.source_tasks)
        etl = next((s for s in sources if task_type_from_id(s) == TaskType.ETL), None)
        if paths["input"] is None:
            prediction = p.source_task(TaskType.PREDICT)
            paths["input"], metadata = self.source_file(prediction, "predictions")
            PredictionProtocol.model_validate(metadata["output_params"]["protocol"])
            etl = etl or metadata["output_params"]["protocol"]["market_source_task"]
        if etl:
            for key in ("market", "calendar", "labels"):
                if paths[key] is None:
                    paths[key] = self.source_file(etl, key)[0]
        if paths["market"] is None or paths["calendar"] is None:
            raise ValueError("Backtest requires independent market and calendar artifacts")
        paths = {key: self.resolve_workspace_path(value) for key, value in paths.items() if value is not None}
        self.state["input_paths"] = paths
        self.state["input_revisions"] = {key: file_revision(value) for key, value in paths.items()}
        self.state["signals"] = pl.read_parquet(paths["input"])

    def fixed_holding_days(self) -> int | None:
        return self.input_params.holding_days

    def portfolio_policy(self) -> PortfolioPolicy | None:
        """Override in a plugin to supply decisions to the shared execution ledger."""
        return None

    def build_universes(self) -> Iterable[BacktestUniverse]:
        """Declare independent reports. Plugins own names and selection rules."""
        yield BacktestUniverse(key="all", label="All market")

    # Extension hooks keep the universe argument available to plugin overrides.
    # pylint: disable=unused-argument
    def select_universe(self, signals: pl.DataFrame, universe: BacktestUniverse) -> pl.DataFrame:
        """Return prediction keys only; labels and future market data are unavailable here."""
        return signals.select(*KEYS)

    def prepare_signals(self) -> None:
        """Plugins may aggregate declared model scores before evaluating every universe."""

    def market_data(self) -> pl.DataFrame:
        return pl.read_parquet(self.state["input_paths"]["market"])

    def universe_events(self, universe: BacktestUniverse):
        """Create independent event state for each universe."""
        return None

    def engine_config(self) -> BacktestConfig:
        return PortfolioSettings.engine_config(self.input_params, holding_days=self.fixed_holding_days())

    def run_universe(self, universe, market, calendar, labels):
        return run_backtest(
            self.state["signals"],
            market,
            calendar,
            labels,
            self.engine_config(),
            as_of_date=self.state["cutoff"],
            policy=self.portfolio_policy(),
            universe_keys=self.select_universe(self.state["signals"], universe),
            events=self.universe_events(universe),
        )

    def calculate(self) -> None:
        self.prepare_signals()
        paths = self.state["input_paths"]
        market, calendar = self.market_data(), pl.read_parquet(paths["calendar"])
        labels = pl.read_parquet(paths["labels"]) if "labels" in paths else None
        self.state["cutoff"] = self.input_params.as_of_date or str(market["trade_date"].max())
        universes = list(self.build_universes())
        if not universes or len({u.key for u in universes}) != len(universes):
            raise ValueError("Universe keys must be nonempty and unique")
        self.state.update(universes={}, artifacts={})
        for universe in universes:
            self.logger.info("Evaluating universe={} label={}", universe.key, universe.label)
            result = self.run_universe(universe, market, calendar, labels)
            self.save_universe(universe, result)
            # Each report is saved before the next ledger is constructed.
            del result

    def save_universe(self, universe, result) -> None:
        artifacts = {}
        for name, frame in result.frames.items():
            path = self.task_dir / "universes" / universe.key / (name + ".parquet")
            atomic_write(
                path,
                lambda temporary, data=frame: data.write_parquet(temporary, compression="zstd"),
            )
            key = f"{universe.key}_{name}"
            self.state["artifacts"][key] = artifact_record(path, self.task_dir)
            artifacts[name] = key
        daily = result.frames["daily"]
        self.state["universes"][universe.key] = BacktestUniverseReport(
            label=universe.label,
            parameters=universe.parameters,
            dimensions=BacktestDimensions(
                top_ns=self.input_params.top_ns,
                holding_detail_top_n=30,
                benchmarks=[BacktestBenchmark(key=k, label=k) for k in result.benchmark_keys],
            ),
            date_range={
                "start": daily["trade_date"].min(),
                "end": daily["trade_date"].max(),
            },
            days=daily.height,
            evaluation_status=result.status,
            artifacts=artifacts,
        )

    def write_outputs(self) -> None:
        for key, digest in self.state["input_revisions"].items():
            if file_revision(self.state["input_paths"][key]) != digest:
                raise ValueError(f"Backtest input changed while evaluating: {key}")

    def build_output_params(self) -> StockBacktestOutput:
        return self.output_cls(
            signals_format=STOCK_SIGNALS_FORMAT,
            default_universe=next(iter(self.state["universes"])),
            universes=self.state["universes"],
            protocol={
                **task_protocol(TaskType.BACKTEST),
                "return_unit": "decimal",
                "valuation": "daily adjusted-price mark to market; confirmed suspension carries last mark"
                + ("; missing quotes are assumed suspended" if self.input_params.missing_market_as_suspension else ""),
                "execution": "same-time quote proxy, sells before buys; no queue/partial-fill guarantee",
                "selection": "plugin universe keys intersect model eligibility and signal-time buyability; "
                "no label filter",
                "fees": "buy_cost_rate/sell_cost_rate on executed notional",
                "cutoff": self.state["cutoff"],
                "settings": self.input_params.model_dump(mode="json", exclude={"task_name", "source_tasks"}),
                "input_revisions": self.state["input_revisions"],
                "allocation": "each target has at most 1/N equity; locked capacity and unfilled slots retain cash",
                "top30_holdings": "signal targets, not actual position book; positions artifact contains live holdings",
                "ic": "fixed-next-market-day raw labels on selected-universe candidates",
                "benchmark_date": "label target date",
                "relative_drawdown": "drawdown of compounded daily net strategy return minus benchmark return; "
                "finite aligned observations only; initial equity 1; reset each summary period",
            },
            artifacts=self.state["artifacts"],
        )
