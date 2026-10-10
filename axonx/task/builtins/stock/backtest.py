"""Standard stock backtest Task: plugins supply artifacts, not copied ledgers."""

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import polars as pl
from pydantic import Field, field_validator

from ....enums import TaskType
from ....utils.fs import atomic_write, file_sha256
from ...contracts import (
    BaseBacktestTask,
    BaseBacktestInputParams,
    BaseBacktestOutputParams,
    BacktestDimensions,
    BacktestBenchmark,
)
from ...core import TaskStep, parse_source_tasks, task_type_from_id
from ...storage import artifact_path, artifact_record, read_metadata
from .data import VERSION
from .engine import BacktestConfig, PortfolioPolicy, run_backtest


class StockPortfolioInput(BaseBacktestInputParams):
    input_file: Path | None = None
    market_file: Path | None = None
    calendar_file: Path | None = None
    labels_file: Path | None = None
    as_of_date: str | None = None
    top_ns: list[int] = Field(default_factory=lambda: [1, 2, 3, 5, 10, 20, 30])
    buy_cost_rate: float = Field(default=0.0005, ge=0, lt=1, description="Fee on executed buy notional.")
    sell_cost_rate: float = Field(default=0.0015, ge=0, lt=1, description="Fee on executed sell notional.")
    annual_risk_free_rate: float = Field(default=0.012, gt=-1, lt=1)
    annualization_days: int = Field(default=252, gt=0)
    minimum_index_weight_coverage: float = Field(default=0.98, gt=0, le=1)
    index_codes: list[str] = Field(default_factory=list)
    missing_market_as_suspension: bool = Field(
        default=False,
        description="Treat absent quotes and missing_data as suspensions: carry the last mark, block trading, "
        "and do not mark evaluation incomplete for these gaps.",
    )

    @field_validator("top_ns")
    @classmethod
    def positive_ns(cls, values: list[int]) -> list[int]:
        if not values or any(n <= 0 for n in values):
            raise ValueError("top_ns must contain positive integers")
        return sorted(set(values))

    @field_validator("index_codes")
    @classmethod
    def indices(cls, values: list[str]) -> list[str]:
        values = [v.strip().lower() for v in values]
        if any(not v for v in values):
            raise ValueError("Empty index code")
        return list(dict.fromkeys(values))

    @field_validator("as_of_date", mode="before")
    @classmethod
    def cutoff(cls, value: object) -> str | None:
        return BaseBacktestTask.normalize_yyyymmdd(value, optional=True)


class StockBacktestInput(StockPortfolioInput):
    holding_days: int = Field(default=1, ge=1)


class StockBacktestOutput(BaseBacktestOutputParams):
    evaluation_status: str
    daily_file: str
    summary_file: str
    targets_file: str
    orders_file: str
    positions_file: str
    trades_file: str


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
        path = artifact_path(root, metadata, name)
        if file_sha256(path) != metadata["output_params"]["artifacts"][name]["sha256"]:
            raise ValueError(f"Source artifact changed: {task_id}/{name}")
        return path, metadata

    def resolve_inputs(self) -> None:
        p = self.input_params
        paths = {key: getattr(p, key + "_file") for key in ("input", "market", "calendar", "labels")}
        sources = parse_source_tasks(p.source_tasks)
        etl = next((s for s in sources if task_type_from_id(s) == TaskType.ETL), None)
        if paths["input"] is None:
            prediction = p.source_task(TaskType.PREDICT)
            paths["input"], metadata = self.source_file(prediction, "predictions")
            if metadata["output_params"]["protocol"].get("version") != VERSION:
                raise ValueError("Unsupported prediction stock protocol version")
            etl = etl or metadata["output_params"]["protocol"]["market_source_task"]
        if etl:
            for key in ("market", "calendar", "labels"):
                if paths[key] is None:
                    paths[key] = self.source_file(etl, key)[0]
        if paths["market"] is None or paths["calendar"] is None:
            raise ValueError("Backtest requires independent market and calendar artifacts")
        paths = {key: self.resolve_workspace_path(value) for key, value in paths.items() if value is not None}
        self.state["input_paths"] = paths
        self.state["input_digests"] = {key: file_sha256(value) for key, value in paths.items()}
        self.state["signals"] = pl.read_parquet(paths["input"])

    def fixed_holding_days(self) -> int | None:
        return self.input_params.holding_days

    def portfolio_policy(self) -> PortfolioPolicy | None:
        """Override in a plugin to supply decisions to the shared execution ledger."""
        return None

    def calculate(self) -> None:
        p = self.input_params
        paths = self.state["input_paths"]
        market, calendar = pl.read_parquet(paths["market"]), pl.read_parquet(paths["calendar"])
        labels = pl.read_parquet(paths["labels"]) if "labels" in paths else None
        self.state["cutoff"] = p.as_of_date or str(market["trade_date"].max())
        self.state["result"] = run_backtest(
            self.state["signals"],
            market,
            calendar,
            labels,
            BacktestConfig(
                top_ns=tuple(p.top_ns),
                holding_days=self.fixed_holding_days(),
                buy_cost_rate=p.buy_cost_rate,
                sell_cost_rate=p.sell_cost_rate,
                annual_risk_free_rate=p.annual_risk_free_rate,
                annualization_days=p.annualization_days,
                minimum_index_weight_coverage=p.minimum_index_weight_coverage,
                index_codes=tuple(p.index_codes),
                missing_market_as_suspension=p.missing_market_as_suspension,
            ),
            as_of_date=self.state["cutoff"],
            policy=self.portfolio_policy(),
        )

    def write_outputs(self) -> None:
        for key, digest in self.state["input_digests"].items():
            if file_sha256(self.state["input_paths"][key]) != digest:
                raise ValueError(f"Backtest input changed while evaluating: {key}")
        self.state["paths"] = {}
        for name, frame in self.state["result"].frames.items():
            path = self.task_dir / (name + ".parquet")
            atomic_write(
                path,
                lambda temporary, data=frame: data.write_parquet(temporary, compression="zstd"),
            )
            self.state["paths"][name] = path

    def build_output_params(self) -> StockBacktestOutput:
        daily = self.state["result"].frames["daily"]
        return self.output_cls(
            evaluation_status=self.state["result"].status,
            dimensions=BacktestDimensions(
                top_ns=self.input_params.top_ns,
                holding_detail_top_n=30,
                benchmarks=[BacktestBenchmark(key=k, label=k) for k in self.state["result"].benchmark_keys],
            ),
            protocol={
                "version": VERSION,
                "return_unit": "decimal",
                "valuation": "daily adjusted-price mark to market; confirmed suspension carries last mark"
                + ("; missing quotes are assumed suspended" if self.input_params.missing_market_as_suspension else ""),
                "execution": "same-time quote proxy, sells before buys; no queue/partial-fill guarantee",
                "selection": "signal candidates first; no future-label filter or replacement for unfilled targets",
                "fees": "buy_cost_rate/sell_cost_rate on executed notional",
                "cutoff": self.state["cutoff"],
                "settings": self.input_params.model_dump(mode="json", exclude={"task_name", "source_tasks"}),
                "input_sha256": self.state["input_digests"],
                "allocation": "each target has at most 1/N equity; locked capacity and unfilled slots retain cash",
                "top30_holdings": "signal targets, not actual position book; positions artifact contains live holdings",
                "ic": "fixed-next-market-day raw labels on signal dates",
                "benchmark_date": "label target date",
            },
            date_range={
                "start": daily["trade_date"].min(),
                "end": daily["trade_date"].max(),
            },
            days=daily.height,
            **{name + "_file": str(path) for name, path in self.state["paths"].items()},
            artifacts={name: artifact_record(path, self.task_dir) for name, path in self.state["paths"].items()},
        )
