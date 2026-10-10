"""Train one LightGBM model from an Alpha158 ETL task."""

from __future__ import annotations
import math
from collections.abc import Iterable
from pathlib import Path
from typing import Literal, Self

import numpy as np
import polars as pl
from pydantic import Field, field_validator, model_validator

from axonx.enums import TaskType
from axonx.task.contracts import (
    BaseTrainInputParams,
    BaseTrainOutputParams,
    BaseTrainTask,
)
from axonx.task.core import TaskStep
from axonx.task.builtins.stock.data import VERSION, transform_labels
from axonx.task.storage import artifact_path, artifact_record, read_metadata
from axonx.utils.fs import atomic_write

from .internal.etl_pipeline import CSZ_LABELS, LABELS, RANK_LABELS
from .internal.modeling import feature_matrix
from .internal.reference import DEVIATIONS, QLIB_PARAMETERS, QLIB_REFERENCE

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

    parameter_preset: Literal["axonx", "qlib"] = Field(
        default="axonx",
        description="Hyperparameter defaults only; both presets keep the AxonX labels, validation and refit lifecycle.",
    )
    train_start: str = Field(
        default="20150101",
        description="First training date in YYYYMMDD format, inclusive.",
    )
    train_end: str = Field(default="20230101", description="Training cutoff in YYYYMMDD format, exclusive.")
    label_column: str = Field(
        default="label_return_rank",
        # Default target: daily cross-sectional ranks of T -> T+1 returns.
        # Qlib instead uses T+1/T+2 returns followed by sample-std CSZScoreNorm.
        description="Training target: raw return, daily rank (default), or cross-sectional Z-score.",
    )
    label_winsorize_tail: float = Field(
        default=0.025,
        ge=0,
        lt=0.5,
        description="Fraction clipped from each eligible daily return tail before training-only CSZ normalization.",
    )
    trim_tail: float = Field(
        default=0.025,
        ge=0.0,
        lt=0.5,
        description="Fraction of daily raw-return extremes removed from each tail.",
    )
    validation_ratio: float = Field(
        default=0.10,
        gt=0.0,
        lt=0.5,
        description="Fraction of training dates reserved at the end for validation.",
    )
    num_boost_round: int = Field(
        default=1000,
        gt=0,
        description="Maximum boosting rounds when selecting the best iteration.",
    )
    early_stopping_rounds: int = Field(
        default=50,
        gt=0,
        description="Rounds without validation improvement before stopping.",
    )
    learning_rate: float = Field(default=0.03, gt=0.0, description="Step size applied to each boosting round.")
    num_leaves: int = Field(default=31, ge=2, description="Maximum number of leaves in each tree.")
    max_depth: int = Field(default=-1, ge=-1, description="Maximum tree depth; -1 allows unlimited depth.")
    min_data_in_leaf: int = Field(default=20, gt=0, description="Minimum number of training rows in a leaf.")
    feature_fraction: float = Field(
        default=0.9,
        gt=0.0,
        le=1.0,
        description="Fraction of features sampled for each tree.",
    )
    bagging_fraction: float = Field(
        default=0.9,
        gt=0.0,
        le=1.0,
        description="Fraction of training rows sampled during bagging.",
    )
    bagging_freq: int = Field(
        default=1,
        ge=0,
        description="Boosting rounds between bagging samples; 0 disables bagging.",
    )
    lambda_l1: float = Field(default=0.0, ge=0.0, description="L1 penalty applied to leaf weights.")
    lambda_l2: float = Field(default=0.0, ge=0.0, description="L2 penalty applied to leaf weights.")
    random_seed: int = Field(default=42, ge=0, description="Seed for reproducible LightGBM sampling.")
    num_threads: int = Field(default=8, gt=0, description="Number of CPU threads used by LightGBM.")

    @model_validator(mode="before")
    @classmethod
    def apply_parameter_preset(cls, values: object) -> object:
        """Explicit overrides win; never mutate the caller's input dictionary."""
        if isinstance(values, dict) and values.get("parameter_preset") == "qlib":
            values = {**QLIB_PARAMETERS, **values}
        return values

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
    """Train a LightGBM model on an Alpha158 dataset.

    Uses a time-ordered validation split to select boosting rounds and saves
    the final model, validation metrics, and feature importance.
    """

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
        source_dir = self.source_task_dir(etl_task_id)
        source_metadata_path = source_dir / "metadata.json"
        source_metadata = read_metadata(source_metadata_path)
        if source_metadata["output_params"].get("protocol", {}).get("version") != VERSION:
            raise ValueError("Unsupported ETL stock protocol version")
        dataset_path = artifact_path(source_dir, source_metadata, "dataset")
        output_dir = self.task_dir
        self.state.update(
            source_dir=source_dir,
            source_metadata_path=source_metadata_path,
            source_metadata=source_metadata,
            dataset_path=dataset_path,
            labels_path=artifact_path(source_dir, source_metadata, "labels"),
            model_path=output_dir / "model.txt",
            importance_path=output_dir / "feature_importance.csv",
            history_path=output_dir / "evaluation_history.csv",
        )
        self.logger.info(
            f"Training source resolved etl_task_id={etl_task_id} "
            f"dataset={dataset_path} label={self.input_params.label_column}",
        )

    def load_and_validate_train_data(self) -> None:
        path: Path = self.state["dataset_path"]
        if not path.is_file():
            raise FileNotFoundError(f"Alpha158 数据不存在: {path}")
        features = tuple(self.state["source_metadata"].get("output_params", {}).get("feature_columns", ()))
        if not features:
            raise ValueError("ETL metadata 缺少 feature_columns")
        features = self.select_features(features)
        required = (
            "trade_date",
            "trade_time",
            "ts_code",
            "is_buyable_at_signal",
            *features,
        )
        schema = pl.read_parquet_schema(path)
        if missing := set(required) - set(schema):
            raise ValueError(f"Missing training columns: {sorted(missing)}")
        frame = (
            pl.scan_parquet(path)
            .select(required)
            .join(
                pl.scan_parquet(self.state["labels_path"]),
                on=["trade_date", "trade_time", "ts_code"],
                how="left",
                validate="1:1",
            )
            .filter(
                (pl.col("trade_date") >= self.input_params.train_start)
                & (pl.col("trade_date") < self.input_params.train_end)
                & (pl.col("label_target_date") < self.input_params.train_end)
                & pl.col("label_valid")
                & pl.col("is_buyable_at_signal")
                & pl.col("label_return").is_finite()
            )
            .collect()
            .sort("trade_date", "ts_code")
        )
        if frame.is_empty():
            raise ValueError("No cutoff-safe training labels")
        self.state.update(
            frame=frame,
            features=features,
            valid_label="label_valid",
            loaded_rows=frame.height,
        )

    def select_features(self, features: tuple[str, ...]) -> tuple[str, ...]:
        """Allow derived research plugins to select their feature groups."""
        return features

    def trim_daily_label_tails(self) -> None:
        frame: pl.DataFrame = self.state["frame"]
        raw = pl.col(self.raw_label)
        lower = raw.quantile(self.input_params.trim_tail, interpolation="linear").over("trade_date")
        upper = raw.quantile(1 - self.input_params.trim_tail, interpolation="linear").over("trade_date")
        trimmed = frame.filter(raw.is_between(lower, upper, closed="both"))
        if trimmed.is_empty():
            raise ValueError("每日标签尾部过滤后没有训练样本")
        self.state.update(frame=trimmed, pre_trim_rows=frame.height)
        self.report_progress(95)
        self.logger.info(
            f"Training tails trimmed raw_label={self.raw_label} tail={self.input_params.trim_tail:.2%} "
            f"before={frame.height} after={trimmed.height}",
        )

    def split_temporal_validation(self) -> None:
        # Deliberately retain AxonX's simple one-cutoff workflow instead of Qlib's
        # independent train/valid/test segments. Purge labels crossing the split.
        frame: pl.DataFrame = self.state["frame"]
        dates = frame["trade_date"].unique().sort().to_list()
        if len(dates) < 2:
            raise ValueError("训练至少需要两个有效交易日")
        validation_days = max(1, math.ceil(len(dates) * self.input_params.validation_ratio))
        validation_days = min(validation_days, len(dates) - 1)
        validation_start = dates[-validation_days]
        fit = frame.filter(pl.col("label_target_date") < validation_start)
        validation = frame.filter(pl.col("trade_date") >= validation_start)
        if fit.is_empty() or validation.is_empty():
            raise ValueError("无法构造时间顺序训练/验证集")

        def convert(data: pl.DataFrame) -> pl.DataFrame:
            return transform_labels(
                data,
                reference=pl.lit(True),
                winsorize_tail=self.input_params.label_winsorize_tail,
            )

        frame, fit, validation = convert(frame), convert(fit), convert(validation)
        self.state["frame"] = frame
        self.state.update(
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
            feature_matrix(frame, self.state["features"]),
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
        fit_x, fit_y = self._matrix(self.state["tuning_train"])
        self.report_progress(10)
        valid_x, valid_y = self._matrix(self.state["validation"])
        self.report_progress(20)
        history: dict[str, dict[str, list[float]]] = {}
        train_dataset = lgb.Dataset(
            fit_x,
            label=fit_y,
            feature_name=list(self.state["features"]),
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
        self.state.update(
            tuning_model=model,
            evaluation_history=history,
            best_iteration=best_iteration,
        )
        self.logger.info(
            f"LightGBM tuning completed best_iteration={best_iteration} "
            f"validation_l2={history['validation']['l2'][best_iteration - 1]:.8f}",
        )

    def evaluate_validation(self) -> None:
        validation: pl.DataFrame = self.state["validation"]
        valid_x, valid_y = self._matrix(validation)
        self.report_progress(25)
        pred = np.asarray(
            self.state["tuning_model"].predict(valid_x, num_iteration=self.state["best_iteration"]),
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
        self.state["validation_metrics"] = {
            "l2": float(np.mean(np.square(pred - valid_y))),
            "ic_mean": self._finite_mean(diagnostic["ic"]),
            "rankic_mean": self._finite_mean(diagnostic["rank_ic"]),
        }
        evaluation_history = self.state["evaluation_history"]
        history_columns = {
            f"{dataset}_{metric}": values
            for dataset, metrics in evaluation_history.items()
            for metric, values in metrics.items()
        }
        history_length = len(next(iter(history_columns.values())))
        self.state["history"] = pl.DataFrame(
            {"iteration": range(1, history_length + 1), **history_columns},
        )
        self.report_progress(95)

    def fit_final_model(self) -> None:
        # Unlike Qlib's benchmark, reuse the selected round count to refit all
        # cutoff-safe training rows. Prediction remains after the training cutoff.
        lgb = self._lightgbm()
        full_x, full_y = self._matrix(self.state["frame"])
        self.report_progress(15)
        self.state["model"] = lgb.train(
            self._parameters(),
            lgb.Dataset(full_x, label=full_y, feature_name=list(self.state["features"])),
            num_boost_round=self.state["best_iteration"],
            callbacks=[self._progress_callback(self.state["best_iteration"], "final-fit", start=15)],
        )
        self.state.pop("tuning_model", None)
        self.report_progress(95)
        self.logger.info(f"Final LightGBM fitted rows={len(full_y)} iterations={self.state['best_iteration']}")

    def calculate_feature_importance(self) -> None:
        model = self.state["model"]
        self.state["importance"] = pl.DataFrame(
            {
                "feature": self.state["features"],
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
        atomic_write(
            self.state["model_path"],
            lambda temporary: self.state["model"].save_model(str(temporary)),
        )
        self.report_progress(40)
        outputs = (("importance", "importance_path"), ("history", "history_path"))
        for index, (key, path_key) in enumerate(outputs, start=1):
            path: Path = self.state[path_key]
            atomic_write(path, self.state[key].write_csv)
            self.report_progress(40 + index / len(outputs) * 55)
        self.logger.info(
            f"Training artifacts written model={self.state['model_path']} "
            f"importance={self.state['importance_path']} history={self.state['history_path']}",
        )

    def build_output_params(self) -> LgbmTrainOutputParams:
        output_dir: Path = self.task_dir
        frame: pl.DataFrame = self.state["frame"]
        artifacts = {}
        artifact_paths = (
            ("model", "model_path"),
            ("feature_importance", "importance_path"),
            ("evaluation_history", "history_path"),
        )
        for name, path_key in artifact_paths:
            artifacts[name] = artifact_record(self.state[path_key], output_dir)
        return self.output_cls(
            protocol={
                "qlib_reference": QLIB_REFERENCE,
                "qlib_deviations": {key: DEVIATIONS[key] for key in ("label", "training")},
                "parameter_preset": self.input_params.parameter_preset,
                "train_start_inclusive": self.input_params.train_start,
                "train_end_exclusive": self.input_params.train_end,
                "validation_start_inclusive": self.state["validation_start"],
                "label_column": self.input_params.label_column,
                "version": VERSION,
                "label_transform": {
                    "reference": "cutoff-safe eligible training rows",
                    "winsorize_tail": self.input_params.label_winsorize_tail,
                    "rank": "average (rank-1)/(n-1); singleton=.5",
                    "csz_ddof": 0,
                },
                "raw_label_for_trimming": self.raw_label,
                "daily_trim_tail": self.input_params.trim_tail,
                "prediction_rows_are_not_trimmed": True,
                "sample_filter": (
                    "signal-date buyability, valid fixed-one-day label available before exclusive cutoff, "
                    "label_target_date < train_end; transforms after temporal filtering"
                ),
            },
            feature_columns=list(self.state["features"]),
            target_columns=[self.input_params.label_column],
            model_name="LightGBM",
            metrics={
                name: value
                for name, value in self.state["validation_metrics"].items()
                if isinstance(value, (int, float)) and math.isfinite(value)
            },
            parameters=self._parameters(),
            training_curve={
                "x": [str(iteration) for iteration in self.state["history"]["iteration"].to_list()],
                # L2 is mean squared error and L1 is mean absolute error.
                # Their numeric ranges differ, so training and validation
                # series for each metric share one dedicated y-axis.
                "y_left": {
                    column: self.state["history"][column].to_list()
                    for column in self.state["history"].columns
                    if column.endswith("_l2")
                },
                "y_right": {
                    column: self.state["history"][column].to_list()
                    for column in self.state["history"].columns
                    if column.endswith("_l1")
                },
            },
            model={
                "library": "lightgbm",
                "library_version": self._lightgbm().__version__,
                "parameters": self._parameters(),
                "best_iteration": self.state["best_iteration"],
            },
            rows={
                "loaded": self.state["loaded_rows"],
                "eligible": self.state["pre_trim_rows"],
                "before_trim": self.state["pre_trim_rows"],
                "after_trim": frame.height,
                "tuning_train": self.state["tuning_train"].height,
                "validation": self.state["validation"].height,
            },
            validation_metrics=self.state["validation_metrics"],
            artifacts=artifacts,
            model_files={"model": str(self.state["model_path"])},
            feature_importance_file=str(self.state["importance_path"]),
            evaluation_history_file=str(self.state["history_path"]),
            train_rows=frame.height,
            best_iteration=self.state["best_iteration"],
        )
