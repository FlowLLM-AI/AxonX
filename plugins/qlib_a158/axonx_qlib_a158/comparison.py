"""Compare label and LightGBM presets through observable child Tasks."""

import json
from typing import Literal, Self

import polars as pl
from pydantic import Field, model_validator

from axonx.task.builtins.stock.models import StockBacktestInput, StockPortfolioInput
from axonx.task.core.research import BaseAnalysisTask
from axonx.task.models.identity import TaskType, generated_task_name
from axonx.task.models.params import BaseInputParams
from axonx.task.storage.artifacts import artifact_record
from axonx.task.storage.files import atomic_write, atomic_write_json, file_revision
from axonx.task.storage.inputs import read_upstream_metadata

from .predict import LgbmPredictInputParams
from .train import LgbmTrainInputParams


class ComparisonInputParams(BaseInputParams):
    labels: list[Literal["rank", "csz"]] = Field(default_factory=lambda: ["rank"], min_length=1)
    train: LgbmTrainInputParams = Field(default_factory=LgbmTrainInputParams)
    predict: LgbmPredictInputParams = Field(default_factory=LgbmPredictInputParams)
    portfolio: StockPortfolioInput = Field(default_factory=StockPortfolioInput)
    backtest: StockBacktestInput = Field(default_factory=StockBacktestInput)

    @model_validator(mode="after")
    def validate_stages(self) -> Self:
        self.upstream_task_id(TaskType.ETL)
        for name in ("train", "predict", "portfolio", "backtest"):
            params = getattr(self, name)
            if params.task_name is not None or params.upstream_task_ids:
                raise ValueError(f"Comparison owns {name}.task_name and {name}.upstream_task_ids")
        if {"parameter_preset", "label_column"} & self.train.model_fields_set:
            raise ValueError("Comparison owns train.parameter_preset and train.label_column")
        if any(
            getattr(self.backtest, key) is not None
            for key in ("market_file", "calendar_file", "labels_file", "as_of_date")
        ):
            raise ValueError("Comparison owns the backtest's input artifacts and as_of_date")
        if self.portfolio.input_file is not None or self.portfolio.score_columns is not None:
            raise ValueError("Comparison owns portfolio input artifacts")
        if self.predict.pred_start < self.train.train_end:
            raise ValueError("predict.pred_start must be at or after train.train_end")
        return self


class ParameterComparisonTask(BaseAnalysisTask):
    """Own the comparison report while retaining each stage's identity and parameters."""

    input_cls = ComparisonInputParams
    input_params: ComparisonInputParams

    def build_task_steps(self):
        yield self.compare_parameters

    def compare_parameters(self):
        p = self.input_params
        etl_id = p.upstream_task_id(TaskType.ETL)
        source, metadata = read_upstream_metadata(self.workspace_path, etl_id)
        dataset = metadata["output_params"]["artifacts"]["dataset"]
        records, summaries = {}, []
        labels = list(dict.fromkeys(p.labels))
        for label in labels:
            for preset in ("axonx", "qlib"):
                key = preset if len(labels) == 1 else f"{label}_{preset}"
                name = generated_task_name(self.created_at)
                train = self.run_task(
                    "qlib_a158_train",
                    node_name=f"train-{key}",
                    task_name=name,
                    upstream_task_ids=[etl_id],
                    parameter_preset=preset,
                    label_column=f"label_return_{label}",
                    **p.train.model_dump(
                        mode="json",
                        exclude_unset=True,
                        exclude={"task_name", "upstream_task_ids", "parameter_preset", "label_column"},
                    ),
                )
                prediction = self.run_task(
                    "qlib_a158_predict",
                    node_name=f"predict-{key}",
                    task_name=name,
                    upstream_task_ids=[train.child_task_id],
                    **p.predict.model_dump(mode="json", exclude={"task_name", "upstream_task_ids"}),
                )
                portfolio = self.run_task(
                    "qlib_a158_portfolio",
                    node_name=f"portfolio-{key}",
                    task_name=name,
                    upstream_task_ids=[prediction.child_task_id],
                    **p.portfolio.model_dump(mode="json", exclude={"task_name", "upstream_task_ids"}),
                )
                backtest = self.run_task(
                    "qlib_a158_backtest",
                    node_name=f"backtest-{key}",
                    task_name=name,
                    upstream_task_ids=[portfolio.child_task_id],
                    as_of_date=prediction.output["date_range"]["end"],
                    **p.backtest.model_dump(mode="json", exclude={"task_name", "upstream_task_ids", "as_of_date"}),
                )
                stages = {"train": train, "predict": prediction, "portfolio": portfolio, "backtest": backtest}
                member = next(iter(train.output["model_groups"][0]["models"].values()))
                records[key] = {
                    "label": label,
                    "parameter_preset": preset,
                    "backtest_settings": backtest.output["protocol"]["settings"],
                    "tasks": {stage: result.child_task_id for stage, result in stages.items()},
                    "started_at": {
                        stage: result.record.model_dump(mode="json", include={"started_at"})["started_at"]
                        for stage, result in stages.items()
                    },
                    "parameters": member["model"]["parameters"],
                    "best_iteration": member["model"]["best_iteration"],
                    "metrics": member["metrics"],
                    "evaluation_status": [r["evaluation_status"] for r in backtest.output["portfolios"]],
                    "input_revisions": backtest.output["protocol"]["input_revisions"],
                }
                for report in backtest.output["portfolios"]:
                    artifact = backtest.output["artifacts"][report["artifacts"]["summary"]]
                    path = self.upstream_task_dir(backtest.child_task_id) / artifact["path"]
                    summaries.append(
                        pl.read_parquet(path).with_columns(
                            pl.lit(preset).alias("preset"),
                            pl.lit(label).alias("label"),
                            pl.lit(json.dumps(report["portfolio_id"], sort_keys=True)).alias("portfolio_id"),
                        )
                    )
        for key in ("market", "calendar", "labels"):
            if len({record["input_revisions"].get(key) for record in records.values()}) != 1:
                raise ValueError(f"Comparison inputs differ: {key}")
        if file_revision(source / dataset["path"]) != dataset["revision"]:
            raise ValueError("ETL dataset changed during parameter comparison")
        comparison = {
            "etl_task": etl_id,
            "etl_started_at": metadata["started_at"],
            "dataset_revision": dataset["revision"],
            "settings": p.model_dump(mode="json"),
            "presets": records,
            "selection": "Validation metrics, yearly summaries, transaction costs and evaluation status.",
        }
        summary = pl.concat(summaries)
        atomic_write(self.task_dir / "summary_stats.csv", summary.write_csv)
        atomic_write_json(self.task_dir / "comparison.json", comparison)
        self.state["rows"] = summary.height

    def build_output_params(self):
        return self.output_cls(
            rows=self.state.get("rows", 0),
            artifacts={
                key: artifact_record(self.task_dir / name, self.task_dir)
                for key, name in {"summary": "summary_stats.csv", "comparison": "comparison.json"}.items()
                if (self.task_dir / name).is_file()
            },
        )
