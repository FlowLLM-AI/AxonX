"""Execute immutable portfolio plans and publish accounting and performance reports."""

import polars as pl

from ...core.research import BaseBacktestTask
from ...models.artifacts import task_protocol
from ...models.identity import TaskType, task_type_from_id
from ...models.reports import BacktestBenchmark, BacktestDimensions, BacktestPortfolioReport, PortfolioDefinition
from ...storage.artifacts import artifact_record
from ...storage.files import atomic_write, file_revision
from ...storage.inputs import read_upstream_metadata, upstream_artifacts
from .engine import run_backtest
from .models import StockBacktestInput, StockBacktestOutput
from .portfolio import PortfolioReader, StockStrategy
from .protocol import STOCK_SIGNALS_FORMAT


class BaseStockBacktestTask(BaseBacktestTask):
    input_cls = StockBacktestInput
    output_cls = StockBacktestOutput
    input_params: StockBacktestInput
    plan: PortfolioReader
    portfolios: list[PortfolioDefinition]
    portfolio_task_id: str

    def build_task_steps(self):
        yield self.resolve_inputs
        yield self.calculate
        yield self.write_outputs

    def upstream_file(self, task_id, name):
        _, metadata = read_upstream_metadata(self.workspace_path, task_id)
        (path,) = upstream_artifacts(self, task_id, name, metadata=metadata)
        return path, metadata

    def resolve_inputs(self):
        p = self.input_params
        source = p.upstream_task_id(TaskType.PORTFOLIO)
        self.plan = PortfolioReader(self, source)
        output = self.plan.output
        self.portfolios = output.portfolios
        if p.portfolio_ids is not None:
            if any(identity not in [item.portfolio_id for item in self.portfolios] for identity in p.portfolio_ids):
                raise ValueError("Unknown portfolio identity")
            self.portfolios = [item for item in self.portfolios if item.portfolio_id in p.portfolio_ids]
        paths = {key: getattr(p, key + "_file") for key in ("market", "calendar", "labels")}
        etl = next((s for s in p.upstream_task_ids if task_type_from_id(s) == TaskType.ETL), None)
        etl = etl or output.protocol.get("market_upstream_task_id")
        if etl:
            missing = tuple(key for key, value in paths.items() if value is None)
            if missing:
                _, etl_metadata = read_upstream_metadata(self.workspace_path, etl)
                paths.update(zip(missing, upstream_artifacts(self, etl, *missing, metadata=etl_metadata), strict=True))
        if paths["market"] is None or paths["calendar"] is None:
            raise ValueError("Backtest requires independent market and calendar artifacts")
        self.state["input_paths"] = {
            key: self.resolve_workspace_path(value) for key, value in paths.items() if value is not None
        } | {f"portfolio/{key}": path for key, path in self.plan.paths.items()}
        self.state["evaluation_files"] = {
            key: self.resolve_workspace_path(path) for key, path in self.evaluation_files(p).items()
        }
        self.state["input_paths"].update(self.state["evaluation_files"])
        self.state["input_revisions"] = {key: file_revision(path) for key, path in self.state["input_paths"].items()}
        self.portfolio_task_id = source

    def market_data(self):
        return pl.read_parquet(self.state["input_paths"]["market"])

    @classmethod
    def evaluation_files(cls, _params):
        """External policy inputs whose revisions must be captured by the caller."""
        return {}

    @classmethod
    # Policy files are consumed by plugin overrides through this shared API.
    # pylint: disable=unused-argument
    def evaluate(cls, signals, market, calendar, labels, identity, params, *, as_of_date, files, events=None):
        """Evaluate the published decision rule with the same contract in every workflow."""
        return run_backtest(
            signals,
            market,
            calendar,
            labels,
            cls.engine_config(identity, params),
            as_of_date=as_of_date,
            policy=StockStrategy.model_validate(identity["strategy"]).policy(),
            events=events,
        )

    @staticmethod
    def engine_config(identity, params):
        strategy = StockStrategy.model_validate(identity["strategy"])
        return params.engine_config(top_ns=(identity["top_n"],), holding_days=strategy.holding_days)

    def run_portfolio(self, portfolio, market, calendar, labels):
        return type(self).evaluate(
            self.state["signals"],
            market,
            calendar,
            labels,
            portfolio.portfolio_id,
            self.input_params,
            as_of_date=self.state["cutoff"],
            files=self.state["evaluation_files"],
        )

    def calculate(self):
        paths = self.state["input_paths"]
        market, calendar = self.market_data(), pl.read_parquet(paths["calendar"])
        labels = pl.read_parquet(paths["labels"]) if "labels" in paths else None
        self.state["cutoff"] = self.input_params.as_of_date or str(market["trade_date"].max())
        self.state.update(portfolios=[], artifacts={})
        for portfolio in self.portfolios:
            self.state["signals"] = self.plan.signals(portfolio)
            result = self.run_portfolio(portfolio, market, calendar, labels)
            self.save_portfolio(portfolio, result)

    def save_portfolio(self, portfolio, result):
        artifacts = {}
        index = len(self.state["portfolios"])
        for name, frame in result.frames.items():
            path = self.task_dir / "portfolios" / str(index) / f"{name}.parquet"
            atomic_write(path, lambda temporary, data=frame: data.write_parquet(temporary, compression="zstd"))
            key = f"{index}_{name}"
            self.state["artifacts"][key] = artifact_record(path, self.task_dir)
            artifacts[name] = key
        daily = result.frames["daily"]
        self.state["portfolios"].append(
            BacktestPortfolioReport(
                portfolio_id=portfolio.portfolio_id,
                dimensions=BacktestDimensions(
                    top_ns=[portfolio.portfolio_id["top_n"]],
                    holding_detail_top_n=30,
                    benchmarks=[BacktestBenchmark(key=k, label=k) for k in result.benchmark_keys],
                ),
                date_range={"start": daily["trade_date"].min(), "end": daily["trade_date"].max()},
                days=daily.height,
                evaluation_status=result.status,
                artifacts=artifacts,
            )
        )

    def write_outputs(self):
        for key, digest in self.state["input_revisions"].items():
            if file_revision(self.state["input_paths"][key]) != digest:
                raise ValueError(f"Backtest input changed while evaluating: {key}")

    def build_output_params(self):
        return self.output_cls(
            signals_format=STOCK_SIGNALS_FORMAT,
            portfolios=self.state["portfolios"],
            artifacts=self.state["artifacts"],
            protocol=task_protocol(
                TaskType.BACKTEST,
                portfolio_task_id=self.portfolio_task_id,
                return_unit="decimal",
                execution="Same-time quote proxy; sells before buys; no queue or partial-fill guarantee",
                valuation="Daily adjusted-price mark to market; suspension carries the last mark",
                cutoff=self.state["cutoff"],
                settings=self.input_params.model_dump(mode="json", exclude={"task_name", "upstream_task_ids"}),
                input_revisions=self.state["input_revisions"],
                top30_holdings="Signal targets; actual positions are published separately",
                ic="Fixed-next-market-day raw labels on frozen portfolio candidates",
            ),
        )
