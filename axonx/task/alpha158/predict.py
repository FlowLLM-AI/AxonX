"""Run full-cross-section prediction from an Alpha158 LightGBM training task."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Self

import numpy as np
import polars as pl
from pydantic import field_validator, model_validator

from ...components.registry import R
from ...enums import TaskType
from ..base import BaseConfig, BaseTask, TaskStep
from .internal.artifacts import (
    artifact_path,
    artifact_record,
    atomic_output,
    file_sha256,
    metadata_header,
    normalize_yyyymmdd,
    read_metadata,
    task_directory,
    write_metadata,
)
from .internal.modeling import feature_matrix


class LgbmPredictionConfig(BaseConfig):
    """Configure an out-of-sample prediction interval for a training task."""

    training_task_id: str
    pred_start: str = "20230101"
    pred_end: str | None = None

    @field_validator("pred_start", "pred_end", mode="before")
    @classmethod
    def normalize_date(cls, value: object) -> str | None:
        return normalize_yyyymmdd(value, optional=True)

    @model_validator(mode="after")
    def validate_period(self) -> Self:
        if self.pred_end is not None and self.pred_start > self.pred_end:
            raise ValueError("pred_start 不能晚于 pred_end")
        return self


@R.register("alpha158_lgbm_predict")
class LgbmPredictionTask(BaseTask):
    """Predict every stock in the requested post-training period without label-tail or tradeability filtering."""

    config_cls = LgbmPredictionConfig
    config: LgbmPredictionConfig
    task_type = TaskType.PREDICT
    output_keys = ("predictions_file", "metadata_file", "rows")

    def build_task_steps(self) -> Iterable[TaskStep]:
        yield self.resolve_training_task
        yield self.resolve_source_dataset
        yield self.load_and_validate_prediction_data
        yield self.load_model
        yield self.predict_full_cross_section
        yield self.write_outputs
        yield self.write_metadata
        yield self.publish_output

    def resolve_training_task(self) -> None:
        training_dir = task_directory(self.workspace_path, "training", self.config.training_task_id)
        training_metadata_path = training_dir / "metadata.json"
        training_metadata = read_metadata(training_metadata_path, description="LightGBM training")
        model_path = artifact_path(training_dir, training_metadata, "model")
        train_end = training_metadata.get("protocol", {}).get("train_end_exclusive")
        if not isinstance(train_end, str):
            raise TypeError("训练 metadata 缺少 protocol.train_end_exclusive")
        if self.config.pred_start < train_end:
            raise ValueError(
                f"pred_start 不能早于 train_end: {self.config.pred_start} < {train_end}",
            )
        expected_hash = training_metadata.get("artifact_integrity", {}).get("model", {}).get("sha256")
        if expected_hash and file_sha256(model_path) != expected_hash:
            raise ValueError(f"模型文件 SHA256 与训练 metadata 不一致: {model_path}")
        output_dir = self.workspace_path / "predict" / self.task_id
        self.context.update(
            training_dir=training_dir,
            training_metadata_path=training_metadata_path,
            training_metadata=training_metadata,
            model_path=model_path,
            train_end=train_end,
            output_dir=output_dir,
            predictions_path=output_dir / "predictions.parquet",
            metadata_path=output_dir / "metadata.json",
        )
        self.logger.info(
            f"Prediction training source resolved training_task_id={self.config.training_task_id} "
            f"model={model_path} train_end={train_end}",
        )

    def resolve_source_dataset(self) -> None:
        etl_task_id = self.context["training_metadata"].get("source", {}).get("etl_task_id")
        if not isinstance(etl_task_id, str):
            raise TypeError("训练 metadata 缺少 source.etl_task_id")
        etl_dir = task_directory(self.workspace_path, "etl", etl_task_id)
        etl_metadata_path = etl_dir / "metadata.json"
        etl_metadata = read_metadata(etl_metadata_path, description="Alpha158 ETL")
        dataset_path = artifact_path(etl_dir, etl_metadata, "dataset")
        self.context.update(
            etl_task_id=etl_task_id,
            etl_dir=etl_dir,
            etl_metadata_path=etl_metadata_path,
            etl_metadata=etl_metadata,
            dataset_path=dataset_path,
        )
        self.logger.info(f"Prediction dataset resolved etl_task_id={etl_task_id} dataset={dataset_path}")

    def load_and_validate_prediction_data(self) -> None:
        path: Path = self.context["dataset_path"]
        if not path.is_file():
            raise FileNotFoundError(f"Alpha158 数据不存在: {path}")
        features = tuple(self.context["training_metadata"].get("feature_columns", ()))
        if not features:
            raise ValueError("训练 metadata 缺少 feature_columns")
        schema = pl.read_parquet_schema(path)
        self.report_progress(10)
        index_columns = tuple(column for column in schema if column.startswith("index_weight_"))
        required = (
            "trade_date",
            "ts_code",
            "name",
            "is_buyable",
            "label_1d",
            "label_1d_is_valid",
            *features,
        )
        if missing := [column for column in required if column not in schema]:
            raise ValueError(f"预测数据缺少字段: {', '.join(missing[:20])}")
        latest = pl.scan_parquet(path).select(pl.col("trade_date").max()).collect().item()
        self.report_progress(25)
        pred_end = self.config.pred_end or latest
        if pred_end > latest:
            self.logger.warning(f"pred_end={pred_end} 晚于 ETL 最新日期 {latest}; 将截断到最新日期")
            pred_end = latest
        frame = (
            pl.scan_parquet(path)
            .filter(
                (pl.col("trade_date") >= pl.lit(self.config.pred_start)) & (pl.col("trade_date") <= pl.lit(pred_end)),
            )
            .select(*required, *index_columns)
            .collect()
            .sort("trade_date", "ts_code")
        )
        self.report_progress(80)
        if frame.is_empty():
            raise ValueError(
                f"预测日期范围内没有数据: {self.config.pred_start}..{pred_end}",
            )
        if frame.select("trade_date", "ts_code").n_unique() != frame.height:
            raise ValueError("预测数据包含重复的 trade_date, ts_code")
        self.context.update(
            frame=frame,
            features=features,
            index_columns=index_columns,
            actual_pred_end=pred_end,
        )
        self.report_progress(95)
        self.logger.info(
            f"Prediction data loaded rows={frame.height} dates={frame['trade_date'].n_unique()} "
            f"start={frame['trade_date'].min()} end={frame['trade_date'].max()}",
        )

    def load_model(self) -> None:
        try:
            import lightgbm as lgb
        except ImportError as exc:
            raise RuntimeError("预测需要安装 lightgbm；请重新安装项目依赖") from exc
        model = lgb.Booster(model_file=str(self.context["model_path"]))
        if tuple(model.feature_name()) != self.context["features"]:
            raise ValueError("模型特征名称或顺序与训练 metadata 不一致")
        self.context["model"] = model

    def predict_full_cross_section(self) -> None:
        frame: pl.DataFrame = self.context["frame"]
        matrix = feature_matrix(frame, self.context["features"])
        self.report_progress(30)
        best_iteration = self.context["training_metadata"]["model"]["best_iteration"]
        prediction = np.asarray(
            self.context["model"].predict(matrix, num_iteration=best_iteration),
            dtype=float,
        )
        self.report_progress(80)
        if len(prediction) != frame.height or not np.isfinite(prediction).all():
            raise FloatingPointError("模型预测数量不匹配或包含非有限值")
        self.context["predictions"] = frame.select(
            "trade_date",
            "ts_code",
            pl.Series("pred", prediction),
            pl.col("label_1d").alias("actual_return"),
            pl.col("label_1d_is_valid").alias("label_valid"),
            "name",
            "is_buyable",
            *self.context["index_columns"],
        )
        self.report_progress(95)
        self.logger.info(
            f"Full-cross-section prediction completed rows={len(prediction)} "
            f"pred_min={prediction.min():.8f} pred_max={prediction.max():.8f}",
        )

    def write_outputs(self) -> None:
        output_dir: Path = self.context["output_dir"]
        output_dir.mkdir(parents=True, exist_ok=True)
        path: Path = self.context["predictions_path"]
        atomic_output(
            path,
            lambda temporary: self.context["predictions"].write_parquet(temporary, compression="zstd"),
        )
        self.report_progress(95)
        self.logger.info(
            f"Predictions written path={path} rows={self.context['predictions'].height} bytes={path.stat().st_size}",
        )

    def write_metadata(self) -> None:
        output_dir: Path = self.context["output_dir"]
        predictions: pl.DataFrame = self.context["predictions"]
        prediction_record = artifact_record(self.context["predictions_path"], output_dir)
        self.report_progress(75)
        metadata = {
            **metadata_header(
                task_name="alpha158_lgbm_predict",
                task_id=self.task_id,
                task_type=self.task_type.value,
            ),
            "config": self.config.model_dump(mode="json", exclude={"task_id", "task_type"}),
            "source": {
                "training_task_id": self.config.training_task_id,
                "training_metadata": str(self.context["training_metadata_path"]),
                "etl_task_id": self.context["etl_task_id"],
            },
            "protocol": {
                "train_end_exclusive": self.context["train_end"],
                "pred_start_inclusive": self.config.pred_start,
                "pred_end_inclusive": self.context["actual_pred_end"],
                "cross_section_filter": "none",
                "execution_filter": "deferred to backtest via is_buyable",
                "actual_return_column": "label_1d",
                "actual_return_unit": "decimal",
            },
            "rows": predictions.height,
            "date_range": {
                "start": predictions["trade_date"].min(),
                "end": predictions["trade_date"].max(),
            },
            "model_target": self.context["training_metadata"]["protocol"]["label_column"],
            "index_weight_columns": list(self.context["index_columns"]),
            "artifacts": {"predictions": "predictions.parquet"},
            "artifact_integrity": {
                "predictions": prediction_record,
            },
        }
        write_metadata(self.context["metadata_path"], metadata)
        self.report_progress(95)

    def publish_output(self) -> None:
        self.context.update(
            predictions_file=str(self.context["predictions_path"]),
            metadata_file=str(self.context["metadata_path"]),
            rows=self.context["predictions"].height,
        )
