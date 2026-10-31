"""Compose the Alpha158 research stages through ordinary child Tasks."""

from collections.abc import Iterable
from typing import Self

from pydantic import Field, model_validator

from axonx.task.builtins.stock.models import StockBacktestInput, StockPortfolioInput
from axonx.task.core.base import BaseTask, TaskStep
from axonx.task.models.params import BaseInputParams, BaseOutputParams

from .analysis import FactorAnalysisInputParams
from .etl import Alpha158InputParams
from .predict import LgbmPredictInputParams
from .train import LgbmTrainInputParams


class ResearchInputParams(BaseInputParams):
    etl: Alpha158InputParams = Field(default_factory=lambda: Alpha158InputParams(start_date="20150101"))
    train: LgbmTrainInputParams = Field(default_factory=LgbmTrainInputParams)
    predict: LgbmPredictInputParams = Field(default_factory=LgbmPredictInputParams)
    portfolio: StockPortfolioInput = Field(default_factory=StockPortfolioInput)
    backtest: StockBacktestInput = Field(default_factory=StockBacktestInput)
    analysis: FactorAnalysisInputParams | None = None

    @model_validator(mode="after")
    def validate_chain(self) -> Self:
        if self.upstream_task_ids:
            raise ValueError("Research builds its own ETL; use the leaf Tasks to reuse existing inputs")
        for name in ("etl", "train", "predict", "portfolio", "backtest", "analysis"):
            params = getattr(self, name)
            if params is not None and (params.task_name is not None or params.upstream_task_ids):
                raise ValueError(f"Research owns {name}.task_name and {name}.upstream_task_ids")
        if any(getattr(self.backtest, name) is not None for name in ("market_file", "calendar_file", "labels_file")):
            raise ValueError("Research owns the backtest's input artifacts")
        if self.portfolio.input_file is not None or self.portfolio.score_columns is not None:
            raise ValueError("Research owns portfolio input artifacts")
        if "pred_start" not in self.predict.model_fields_set:
            self.predict.pred_start = self.train.train_end
        if self.predict.pred_start < self.train.train_end:
            raise ValueError("predict.pred_start must be at or after train.train_end")
        return self


class ResearchOutputParams(BaseOutputParams):
    stage_task_ids: dict[str, str]


class Alpha158ResearchTask(BaseTask):
    """Run offline ETL, optional factor analysis, training, prediction, portfolio construction and backtesting.

    Each stage remains an independently observable Task. Nested inputs configure
    the research, while the parent owns child names and dependency references.
    """

    input_cls = ResearchInputParams
    output_cls = ResearchOutputParams

    def build_task_steps(self) -> Iterable[TaskStep]:
        self.state["stage_task_ids"] = {}
        yield self.prepare_dataset
        if self.input_params.analysis is not None:
            yield self.analyze_factors
        yield self.train_model
        yield self.predict
        yield self.portfolio
        yield self.backtest

    def stage(self, name: str, registration: str, params: BaseInputParams, *upstream: str) -> None:
        result = self.run_task(
            registration,
            node_name=name,
            upstream_task_ids=list(upstream),
            **params.model_dump(mode="json", exclude={"task_name", "upstream_task_ids"}),
        )
        self.state["stage_task_ids"][name] = result.child_task_id

    def prepare_dataset(self):
        self.stage("etl", "qlib_a158_etl", self.input_params.etl)

    def analyze_factors(self):
        self.stage("analysis", "qlib_a158_analysis", self.input_params.analysis, self.state["stage_task_ids"]["etl"])

    def train_model(self):
        self.stage("train", "qlib_a158_train", self.input_params.train, self.state["stage_task_ids"]["etl"])

    def predict(self):
        self.stage(
            "predict",
            "qlib_a158_predict",
            self.input_params.predict,
            self.state["stage_task_ids"]["train"],
            self.state["stage_task_ids"]["etl"],
        )

    def portfolio(self):
        self.stage(
            "portfolio", "qlib_a158_portfolio", self.input_params.portfolio, self.state["stage_task_ids"]["predict"]
        )

    def backtest(self):
        self.stage(
            "backtest", "qlib_a158_backtest", self.input_params.backtest, self.state["stage_task_ids"]["portfolio"]
        )

    def build_output_params(self) -> ResearchOutputParams:
        return self.output_cls(stage_task_ids=self.state["stage_task_ids"])
