"""Train one LightGBM model from an Alpha158 ETL task."""

from __future__ import annotations

import math
from collections.abc import Iterable
from pathlib import Path
from typing import Self

import numpy as np
import polars as pl
from pydantic import Field, field_validator, model_validator

from axonx.enums import TaskType
from axonx.task.base import TaskStep
from axonx.task.core import BaseTrainInputParams, BaseTrainOutputParams, BaseTrainTask

from .internal.etl_pipeline import CSZ_LABELS, LABELS, RANK_LABELS
from .internal.modeling import feature_matrix

MODEL_LABELS = (*LABELS, *CSZ_LABELS, *RANK_LABELS)


class LgbmTrainOutputParams(BaseTrainOutputParams):
    feature_importance_file: str
    evaluation_history_file: str
    best_iteration: int
    protocol: dict
    model: dict
    rows: dict[str, int]
    validation_metrics: dict


class LgbmTrainInputParams(BaseTrainInputParams):
    """Configure one time-separated Alpha158 LightGBM training run."""

    train_start: str = "20150101"
    train_end: str = "20230101"
    label_column: str = "label_1d_rank"
    trim_tail: float = Field(default=0.025, ge=0.0, lt=0.5)
    validation_ratio: float = Field(default=0.10, gt=0.0, lt=0.5)
    num_boost_round: int = Field(default=1000, gt=0)
    early_stopping_rounds: int = Field(default=50, gt=0)
    learning_rate: float = Field(default=0.03, gt=0.0)
    num_leaves: int = Field(default=31, ge=2)
    max_depth: int = Field(default=-1, ge=-1)
    min_data_in_leaf: int = Field(default=20, gt=0)
    feature_fraction: float = Field(default=0.9, gt=0.0, le=1.0)
    bagging_fraction: float = Field(default=0.9, gt=0.0, le=1.0)
    bagging_freq: int = Field(default=1, ge=0)
    lambda_l1: float = Field(default=0.0, ge=0.0)
    lambda_l2: float = Field(default=0.0, ge=0.0)
    random_seed: int = Field(default=42, ge=0)
    num_threads: int = Field(default=8, gt=0)

    @field_validator("train_start", "train_end", mode="before")
    @classmethod
    def normalize_date(cls, value: object) -> str:
        return BaseTrainTask.normalize_yyyymmdd(value)

    @field_validator("label_column")
    @classmethod
    def validate_label(cls, value: str) -> str:
        if value not in MODEL_LABELS:
            raise ValueError(f"label_column 必须是: {', '.join(MODEL_LABELS)}")
        return value

    @model_validator(mode="after")
    def validate_period(self) -> Self:
        if self.train_start >= self.train_end:
            raise ValueError("train_start 必须早于 train_end")
        return self


class LgbmTrainTask(BaseTrainTask):
    """Select a label, trim its daily raw-return tails, tune temporally, and fit a native LightGBM booster."""

    input_cls = LgbmTrainInputParams
    output_cls = LgbmTrainOutputParams
    input_params: LgbmTrainInputParams

    def build_task_steps(self) -> Iterable[TaskStep]:
        yield self.resolve_upstream_task
        yield self.load_and_validate_train_data
        yield self.trim_daily_label_tails
        yield self.split_temporal_validation
        yield self.select_best_iteration
        yield self.evaluate_validation
        yield self.fit_final_model
        yield self.calculate_feature_importance
        yield self.write_outputs

    @property
    def raw_label(self) -> str:
        return self.input_params.label_column.removesuffix("_rank").removesuffix("_csz")

    def resolve_upstream_task(self) -> None:
        etl_task_id = self.input_params.source_task(TaskType.ETL)
        source_dir = self.artifact_store.task_directory("etl", etl_task_id)
        source_metadata_path = source_dir / "metadata.json"
        source_metadata = self.artifact_store.read_metadata(source_metadata_path, description="Alpha158 ETL")
        dataset_path = self.artifact_store.artifact_path(source_dir, source_metadata, "dataset")
        output_dir = self.task_dir
        self.context.update(
            source_dir=source_dir,
            source_metadata_path=source_metadata_path,
            source_metadata=source_metadata,
            dataset_path=dataset_path,
            model_path=output_dir / "model.txt",
            importance_path=output_dir / "feature_importance.csv",
            history_path=output_dir / "evaluation_history.csv",
        )
        self.logger.info(
            f"Training source resolved etl_task_id={etl_task_id} "
            f"dataset={dataset_path} label={self.input_params.label_column}",
        )

    def load_and_validate_train_data(self) -> None:
        path: Path = self.context["dataset_path"]
        if not path.is_file():
            raise FileNotFoundError(f"Alpha158 数据不存在: {path}")
        features = tuple(self.context["source_metadata"].get("output_params", {}).get("feature_columns", ()))
        if not features:
            raise ValueError("ETL metadata 缺少 feature_columns")
        valid_label = f"{self.raw_label}_is_valid"
        schema = pl.read_parquet_schema(path)
        self.report_progress(10)
        required = (
            "trade_date",
            "ts_code",
            "is_buyable",
            self.raw_label,
            self.input_params.label_column,
            valid_label,
            *features,
        )
        if missing := [column for column in required if column not in schema]:
            raise ValueError(f"训练数据缺少字段: {', '.join(missing[:20])}")
        frame = (
            pl.scan_parquet(path)
            .filter(
                (pl.col("trade_date") >= pl.lit(self.input_params.train_start))
                & (pl.col("trade_date") < pl.lit(self.input_params.train_end)),
            )
            .select(*required)
            .collect()
            .sort("trade_date", "ts_code")
        )
        self.report_progress(75)
        if frame.is_empty():
            raise ValueError("训练日期范围内没有数据")
        loaded_rows = frame.height
        frame = frame.filter(
            pl.col("is_buyable")
            & pl.col(valid_label)
            & pl.col(self.raw_label).is_finite()
            & pl.col(self.input_params.label_column).is_finite(),
        )
        if frame.is_empty():
            raise ValueError("训练日期范围内没有有效标签")
        self.context.update(
            frame=frame,
            features=features,
            valid_label=valid_label,
            loaded_rows=loaded_rows,
        )
        self.report_progress(95)
        self.logger.info(
            f"Training data loaded rows={frame.height} dates={frame['trade_date'].n_unique()} "
            f"start={frame['trade_date'].min()} end={frame['trade_date'].max()}",
        )

    def trim_daily_label_tails(self) -> None:
        frame: pl.DataFrame = self.context["frame"]
        raw = pl.col(self.raw_label)
        lower = raw.quantile(self.input_params.trim_tail, interpolation="linear").over("trade_date")
        upper = raw.quantile(1 - self.input_params.trim_tail, interpolation="linear").over("trade_date")
        trimmed = frame.filter(raw.is_between(lower, upper, closed="both"))
        if trimmed.is_empty():
            raise ValueError("每日标签尾部过滤后没有训练样本")
        self.context.update(frame=trimmed, pre_trim_rows=frame.height)
        self.report_progress(95)
        self.logger.info(
            f"Training tails trimmed raw_label={self.raw_label} tail={self.input_params.trim_tail:.2%} "
            f"before={frame.height} after={trimmed.height}",
        )

    def split_temporal_validation(self) -> None:
        frame: pl.DataFrame = self.context["frame"]
        dates = frame["trade_date"].unique().sort().to_list()
        if len(dates) < 2:
            raise ValueError("训练至少需要两个有效交易日")
        validation_days = max(1, math.ceil(len(dates) * self.input_params.validation_ratio))
        validation_days = min(validation_days, len(dates) - 1)
        validation_start = dates[-validation_days]
        fit = frame.filter(pl.col("trade_date") < validation_start)
        validation = frame.filter(pl.col("trade_date") >= validation_start)
        if fit.is_empty() or validation.is_empty():
            raise ValueError("无法构造时间顺序训练/验证集")
        self.context.update(
            tuning_train=fit,
            validation=validation,
            validation_start=validation_start,
        )
        self.logger.info(
            f"Temporal validation split train_rows={fit.height} validation_rows={validation.height} "
            f"validation_start={validation_start}",
        )

    def _matrix(self, frame: pl.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        return (
            feature_matrix(frame, self.context["features"]),
            frame[self.input_params.label_column].cast(pl.Float64).to_numpy(),
        )

    def _parameters(self) -> dict[str, object]:
        return {
            "objective": "regression",
            "metric": ["l2", "l1"],
            "learning_rate": self.input_params.learning_rate,
            "num_leaves": self.input_params.num_leaves,
            "max_depth": self.input_params.max_depth,
            "min_data_in_leaf": self.input_params.min_data_in_leaf,
            "feature_fraction": self.input_params.feature_fraction,
            "bagging_fraction": self.input_params.bagging_fraction,
            "bagging_freq": self.input_params.bagging_freq,
            "lambda_l1": self.input_params.lambda_l1,
            "lambda_l2": self.input_params.lambda_l2,
            "seed": self.input_params.random_seed,
            "feature_fraction_seed": self.input_params.random_seed,
            "bagging_seed": self.input_params.random_seed,
            "data_random_seed": self.input_params.random_seed,
            "num_threads": self.input_params.num_threads,
            "deterministic": True,
            "force_col_wise": True,
            "verbosity": -1,
        }

    @staticmethod
    def _lightgbm():
        try:
            import lightgbm as lgb
        except ImportError as exc:
            raise RuntimeError("训练需要安装 lightgbm；请重新安装项目依赖") from exc
        return lgb

    def _progress_callback(self, total: int, phase: str, *, start: float = 0, end: float = 95):
        last_milestone = -1

        def callback(environment) -> None:
            nonlocal last_milestone
            completed = environment.iteration + 1
            milestone = completed * 10 // total
            if completed == 1 or milestone > last_milestone or completed == total:
                last_milestone = milestone
                self.report_progress(start + completed / total * (end - start))
                self.logger.info(f"LightGBM {phase} progress iteration={completed}/{total}")

        callback.order = 5
        callback.before_iteration = False
        return callback

    def select_best_iteration(self) -> None:
        lgb = self._lightgbm()
        fit_x, fit_y = self._matrix(self.context["tuning_train"])
        self.report_progress(10)
        valid_x, valid_y = self._matrix(self.context["validation"])
        self.report_progress(20)
        history: dict[str, dict[str, list[float]]] = {}
        train_dataset = lgb.Dataset(
            fit_x,
            label=fit_y,
            feature_name=list(self.context["features"]),
        )
        validation_dataset = lgb.Dataset(valid_x, label=valid_y, reference=train_dataset)
        model = lgb.train(
            self._parameters(),
            train_dataset,
            num_boost_round=self.input_params.num_boost_round,
            valid_sets=[train_dataset, validation_dataset],
            valid_names=["train", "validation"],
            callbacks=[
                self._progress_callback(self.input_params.num_boost_round, "tuning", start=20),
                lgb.early_stopping(
                    self.input_params.early_stopping_rounds,
                    first_metric_only=True,
                    verbose=False,
                ),
                lgb.record_evaluation(history),
            ],
        )
        best_iteration = model.best_iteration or self.input_params.num_boost_round
        self.context.update(
            tuning_model=model,
            evaluation_history=history,
            best_iteration=best_iteration,
        )
        self.logger.info(
            f"LightGBM tuning completed best_iteration={best_iteration} "
            f"validation_l2={history['validation']['l2'][best_iteration - 1]:.8f}",
        )

    def evaluate_validation(self) -> None:
        validation: pl.DataFrame = self.context["validation"]
        valid_x, valid_y = self._matrix(validation)
        self.report_progress(25)
        pred = np.asarray(
            self.context["tuning_model"].predict(valid_x, num_iteration=self.context["best_iteration"]),
            dtype=float,
        )
        self.report_progress(65)
        diagnostic = (
            pl.DataFrame(
                {
                    "trade_date": validation["trade_date"],
                    "pred": pred,
                    "actual": valid_y,
                },
            )
            .group_by("trade_date")
            .agg(
                pl.corr("pred", "actual", method="pearson").alias("ic"),
                pl.corr("pred", "actual", method="spearman").alias("rank_ic"),
            )
        )
        self.context["validation_metrics"] = {
            "l2": float(np.mean(np.square(pred - valid_y))),
            "ic_mean": self._finite_mean(diagnostic["ic"]),
            "rankic_mean": self._finite_mean(diagnostic["rank_ic"]),
        }
        evaluation_history = self.context["evaluation_history"]
        history_columns = {
            f"{dataset}_{metric}": values
            for dataset, metrics in evaluation_history.items()
            for metric, values in metrics.items()
        }
        history_length = len(next(iter(history_columns.values())))
        self.context["history"] = pl.DataFrame(
            {"iteration": range(1, history_length + 1), **history_columns},
        )
        self.report_progress(95)

    def fit_final_model(self) -> None:
        lgb = self._lightgbm()
        full_x, full_y = self._matrix(self.context["frame"])
        self.report_progress(15)
        self.context["model"] = lgb.train(
            self._parameters(),
            lgb.Dataset(full_x, label=full_y, feature_name=list(self.context["features"])),
            num_boost_round=self.context["best_iteration"],
            callbacks=[self._progress_callback(self.context["best_iteration"], "final-fit", start=15)],
        )
        self.context.pop("tuning_model", None)
        self.report_progress(95)
        self.logger.info(f"Final LightGBM fitted rows={len(full_y)} iterations={self.context['best_iteration']}")

    def calculate_feature_importance(self) -> None:
        model = self.context["model"]
        self.context["importance"] = pl.DataFrame(
            {
                "feature": self.context["features"],
                "importance_gain": model.feature_importance(importance_type="gain"),
                "importance_split": model.feature_importance(importance_type="split"),
            },
        ).sort("importance_gain", descending=True)

    @staticmethod
    def _finite_mean(values: pl.Series) -> float:
        array = values.cast(pl.Float64, strict=False).to_numpy()
        array = array[np.isfinite(array)]
        return float(array.mean()) if len(array) else math.nan

    def write_outputs(self) -> None:
        output_dir: Path = self.task_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        self.artifact_store.atomic_output(
            self.context["model_path"],
            lambda temporary: self.context["model"].save_model(str(temporary)),
        )
        self.report_progress(40)
        outputs = (("importance", "importance_path"), ("history", "history_path"))
        for index, (key, path_key) in enumerate(outputs, start=1):
            path: Path = self.context[path_key]
            self.artifact_store.atomic_output(path, self.context[key].write_csv)
            self.report_progress(40 + index / len(outputs) * 55)
        self.logger.info(
            f"Training artifacts written model={self.context['model_path']} "
            f"importance={self.context['importance_path']} history={self.context['history_path']}",
        )

    def build_output_params(self) -> LgbmTrainOutputParams:
        output_dir: Path = self.task_dir
        frame: pl.DataFrame = self.context["frame"]
        artifacts = {}
        artifact_paths = (
            ("model", "model_path"),
            ("feature_importance", "importance_path"),
            ("evaluation_history", "history_path"),
        )
        for index, (name, path_key) in enumerate(artifact_paths, start=1):
            artifacts[name] = self.artifact_store.artifact_record(self.context[path_key], output_dir)
        return self.output_cls(
            protocol={
                "train_start_inclusive": self.input_params.train_start,
                "train_end_exclusive": self.input_params.train_end,
                "validation_start_inclusive": self.context["validation_start"],
                "label_column": self.input_params.label_column,
                "raw_label_for_trimming": self.raw_label,
                "daily_trim_tail": self.input_params.trim_tail,
                "prediction_rows_are_not_trimmed": True,
                "sample_filter": "is_buyable and valid finite label",
            },
            feature_columns=list(self.context["features"]),
            target_columns=[self.input_params.label_column],
            model_name="LightGBM",
            metrics={
                name: value for name, value in self.context["validation_metrics"].items()
                if isinstance(value, (int, float)) and math.isfinite(value)
            },
            parameters=self._parameters(),
            training_curve={
                "x": [str(iteration) for iteration in self.context["history"]["iteration"].to_list()],
                "y": {
                    column: self.context["history"][column].to_list()
                    for column in self.context["history"].columns
                    if column != "iteration"
                },
            },
            model={
                "library": "lightgbm",
                "library_version": self._lightgbm().__version__,
                "parameters": self._parameters(),
                "best_iteration": self.context["best_iteration"],
            },
            rows={
                "loaded": self.context["loaded_rows"],
                "eligible": self.context["pre_trim_rows"],
                "before_trim": self.context["pre_trim_rows"],
                "after_trim": frame.height,
                "tuning_train": self.context["tuning_train"].height,
                "validation": self.context["validation"].height,
            },
            validation_metrics=self.context["validation_metrics"],
            artifacts=artifacts,
            model_file=str(self.context["model_path"]),
            feature_importance_file=str(self.context["importance_path"]),
            evaluation_history_file=str(self.context["history_path"]),
            train_rows=frame.height,
            best_iteration=self.context["best_iteration"],
        )
