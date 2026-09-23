"""Backtest Alpha158 prediction artifacts with equal-weight top-N portfolios."""

from collections.abc import Iterable
from pathlib import Path

import polars as pl
from pydantic import Field, field_validator

from axonx.enums import TaskType
from axonx.task.contracts import (
    BacktestBenchmark,
    BacktestDimensions,
    BaseBacktestInputParams,
    BaseBacktestOutputParams,
    BaseBacktestTask,
)
from axonx.task.core import TaskStep
from axonx.task.storage import artifact_path, artifact_record, read_metadata
from axonx.utils.fs import atomic_write

from .internal.backtest import (
    HOLDING_DETAIL_TOP_N,
    TOP_NS,
    BacktestConfig,
    BacktestResult,
    run_backtest,
)


class Alpha158BacktestInputParams(BaseBacktestInputParams):
    transaction_cost_rate: float = Field(
        default=0.002,
        ge=0.0,
        lt=1.0,
        description="Decimal transaction cost applied to daily portfolio turnover.",
    )
    annual_risk_free_rate: float = Field(
        default=0.012,
        gt=-1.0,
        lt=1.0,
        description="Annual risk-free rate used for risk-adjusted returns.",
    )
    annualization_days: int = Field(
        default=252,
        gt=0,
        description="Trading days used to annualize return and risk metrics.",
    )
    minimum_index_weight_coverage: float = Field(
        default=0.90,
        gt=0.0,
        le=1.0,
        description="Minimum daily weight coverage required for index benchmarks.",
    )
    index_codes: list[str] = Field(
        default_factory=list,
        description="Optional index codes used to restrict candidates, such as hs300.",
    )

    @field_validator("index_codes")
    @classmethod
    def normalize_index_codes(cls, values: list[str]) -> list[str]:
        normalized = [value.strip().lower() for value in values]
        if any(not value for value in normalized):
            raise ValueError("index_codes cannot contain empty values")
        return list(dict.fromkeys(normalized))


class Alpha158BacktestTask(BaseBacktestTask):
    """Evaluate Alpha158 predictions using daily equal-weight top-N portfolios."""

    input_cls = Alpha158BacktestInputParams
    input_params: Alpha158BacktestInputParams

    REQUIRED_COLUMNS = (
        "trade_date",
        "ts_code",
        "name",
        "pred",
        "actual_return",
        "label_valid",
        "is_buyable",
        "entry_is_buyable",
        "exit_is_sellable",
        "entry_date",
        "exit_date",
    )

    def build_task_steps(self) -> Iterable[TaskStep]:
        yield self.resolve_prediction_artifact
        yield self.load_predictions
        yield self.calculate_backtest
        yield self.write_artifacts

    def resolve_prediction_artifact(self) -> None:
        prediction_task_id = self.input_params.source_task(TaskType.PREDICT)
        source_dir = self.source_task_dir(prediction_task_id)
        metadata = read_metadata(source_dir / "metadata.json")
        if (
            metadata.get("output_params", {})
            .get("protocol", {})
            .get("actual_return_unit")
            != "decimal"
        ):
            raise ValueError("Backtest requires decimal actual returns")
        self.state.update(
            predictions_path=artifact_path(source_dir, metadata, "predictions"),
            daily_path=self.task_dir / "daily.parquet",
            summary_path=self.task_dir / "summary.parquet",
        )

    def load_predictions(self) -> None:
        path: Path = self.state["predictions_path"]
        if not path.is_file():
            raise FileNotFoundError(f"预测文件不存在: {path}")
        schema = pl.read_parquet_schema(path)
        if missing := [name for name in self.REQUIRED_COLUMNS if name not in schema]:
            raise ValueError(f"预测文件缺少字段: {', '.join(missing)}")
        for name in ("label_valid", "is_buyable", "entry_is_buyable", "exit_is_sellable"):
            if schema[name] != pl.Boolean:
                raise TypeError(f"{name} 必须是 Boolean")
        index_columns = tuple(
            name for name in schema if name.startswith("index_weight_")
        )
        self.state.update(
            index_columns=index_columns,
            predictions=(
                pl.scan_parquet(path)
                .select(
                    pl.col("trade_date", "ts_code", "name", "entry_date", "exit_date").cast(pl.String),
                    pl.col("pred", "actual_return", *index_columns).cast(
                        pl.Float64,
                        strict=False,
                    ),
                    "label_valid",
                    "is_buyable",
                    "entry_is_buyable",
                    "exit_is_sellable",
                )
                .collect()
                .sort("trade_date", "ts_code")
            ),
        )
        self.report_progress(95)

    def calculate_backtest(self) -> None:
        self.state["result"] = run_backtest(
            self.state["predictions"],
            self.state["index_columns"],
            BacktestConfig(
                transaction_cost_rate=self.input_params.transaction_cost_rate,
                annual_risk_free_rate=self.input_params.annual_risk_free_rate,
                annualization_days=self.input_params.annualization_days,
                minimum_index_weight_coverage=self.input_params.minimum_index_weight_coverage,
                index_codes=tuple(self.input_params.index_codes),
            ),
        )
        self.report_progress(95)

    def write_artifacts(self) -> None:
        result: BacktestResult = self.state["result"]
        for index, (path, frame) in enumerate(
            (
                (self.state["daily_path"], result.daily),
                (self.state["summary_path"], result.summary),
            ),
            start=1,
        ):
            atomic_write(
                path,
                lambda temporary, output=frame: output.write_parquet(
                    temporary,
                    compression="zstd",
                ),
            )
            self.report_progress(index / 2 * 95)

    def build_output_params(self) -> BaseBacktestOutputParams:
        result: BacktestResult = self.state["result"]
        return self.output_cls(
            dimensions=BacktestDimensions(
                top_ns=list(TOP_NS),
                holding_detail_top_n=HOLDING_DETAIL_TOP_N,
                benchmarks=[
                    BacktestBenchmark(
                        key=key,
                        label="全市场平均" if key == "universe" else key.upper(),
                    )
                    for key in result.benchmark_keys
                ],
            ),
            protocol={
                "actual_return": "adjusted entry_date open to exit_date open; trade_date is signal date",
                "candidate_filter": "signal-date is_buyable and finite prediction; selected index_weight_* > 0",
                "execution": "rank before next-open fill; unfilled entries remain cash; refuse positions without a sellable exit open",
                "index_codes": self.input_params.index_codes,
                "portfolio": "daily equal-weight top-N ranked by descending prediction",
                "initial_turnover": "invested fraction of the initial target portfolio",
                "turnover": "half L1 distance between consecutive filled portfolios, including cash",
                "net_return": "gross return minus turnover times transaction_cost_rate",
                "ic": "daily Pearson correlation in the candidate universe",
                "rank_ic": "daily Spearman correlation in the candidate universe",
                "ndcg": "actual-return cross-sectional percentile relevance in the candidate universe",
                "icir": "annualized mean divided by sample standard deviation",
                "return_period_date": "exit_date; daily.trade_date is the signal date",
            },
            date_range={
                "start": result.daily["trade_date"].min(),
                "end": result.daily["trade_date"].max(),
            },
            days=result.daily.height,
            artifacts={
                name: artifact_record(self.state[f"{name}_path"], self.task_dir)
                for name in ("daily", "summary")
            },
        )
