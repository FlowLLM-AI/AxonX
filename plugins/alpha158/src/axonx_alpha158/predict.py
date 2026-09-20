"""Run full-cross-section prediction from an Alpha158 LightGBM training task."""

from __future__ import annotations
from collections.abc import Iterable
from pathlib import Path
from typing import Self

import numpy as np
import polars as pl
from pydantic import Field, field_validator, model_validator

from axonx.enums import TaskType
from axonx.task.contracts import (
    BasePredictInputParams,
    BasePredictOutputParams,
    BasePredictTask,
)
from axonx.task.core import TaskStep, task_type_from_id
from axonx.task.storage import artifact_path, artifact_record, read_metadata
from axonx.utils.fs import atomic_write, file_sha256

from .internal.modeling import feature_matrix


class LgbmPredictOutputParams(BasePredictOutputParams):
    model_target: str
    index_weight_columns: list[str]


class LgbmPredictInputParams(BasePredictInputParams):
    """Configure an out-of-sample prediction interval for a training task."""

    pred_start: str = Field(default="20230101", description="First prediction date in YYYYMMDD format; must follow the training period.")
    pred_end: str | None = Field(default=None, description="Last prediction date in YYYYMMDD format; omit for the latest dataset date.")

    @field_validator("pred_start", "pred_end", mode="before")
    @classmethod
    def normalize_date(cls, value: object) -> str | None:
        return BasePredictTask.normalize_yyyymmdd(value, optional=True)

    @model_validator(mode="after")
    def validate_period(self) -> Self:
        if self.pred_end is not None and self.pred_start > self.pred_end:
            raise ValueError("pred_start 不能晚于 pred_end")
        return self


class LgbmPredictTask(BasePredictTask):
    """Score stocks after training with the saved Alpha158 LightGBM model.

    Outputs the full prediction cross section for the selected date range,
    including stocks without a valid return label or buyable status.
    """

    input_cls = LgbmPredictInputParams
    output_cls = LgbmPredictOutputParams
    input_params: LgbmPredictInputParams

    def build_task_steps(self) -> Iterable[TaskStep]:
        yield self.resolve_train_task
        yield self.resolve_source_dataset
        yield self.load_and_validate_prediction_data
        yield self.load_model
        yield self.predict_full_cross_section
        yield self.write_outputs

    def resolve_train_task(self) -> None:
        train_task_id = self.input_params.source_task(TaskType.TRAIN)
        train_dir = self.source_task_dir(train_task_id)
        train_metadata_path = train_dir / "metadata.json"
        train_metadata = read_metadata(train_metadata_path)
        model_path = artifact_path(train_dir, train_metadata, "model")
        train_end = train_metadata.get("output_params", {}).get("protocol", {}).get("train_end_exclusive")
        if not isinstance(train_end, str):
            raise TypeError("训练 metadata 缺少 protocol.train_end_exclusive")
        if self.input_params.pred_start < train_end:
            raise ValueError(
                f"pred_start 不能早于 train_end: {self.input_params.pred_start} < {train_end}",
            )
        expected_hash = train_metadata.get("output_params", {}).get("artifacts", {}).get("model", {}).get("sha256")
        if expected_hash and file_sha256(model_path) != expected_hash:
            raise ValueError(f"模型文件 SHA256 与训练 metadata 不一致: {model_path}")
        output_dir = self.task_dir
        self.state.update(
            train_dir=train_dir,
            train_metadata_path=train_metadata_path,
            train_metadata=train_metadata,
            model_path=model_path,
            train_end=train_end,
            predictions_path=output_dir / "predictions.parquet",
        )
        self.logger.info(
            f"Prediction training source resolved train_task_id={train_task_id} "
            f"model={model_path} train_end={train_end}",
        )

    def resolve_source_dataset(self) -> None:
        sources = self.state["train_metadata"].get("input_params", {}).get("source_tasks", [])
        etl_sources = [task_id for task_id in sources if task_type_from_id(task_id) == TaskType.ETL]
        if len(etl_sources) != 1:
            raise ValueError("训练 metadata 必须包含一个 ETL 上游任务")
        etl_task_id = etl_sources[0]
        etl_dir = self.source_task_dir(etl_task_id)
        etl_metadata_path = etl_dir / "metadata.json"
        etl_metadata = read_metadata(etl_metadata_path)
        dataset_path = artifact_path(etl_dir, etl_metadata, "dataset")
        self.state.update(
            etl_task_id=etl_task_id,
            etl_dir=etl_dir,
            etl_metadata_path=etl_metadata_path,
            etl_metadata=etl_metadata,
            dataset_path=dataset_path,
        )
        self.logger.info(f"Prediction dataset resolved etl_task_id={etl_task_id} dataset={dataset_path}")

    def load_and_validate_prediction_data(self) -> None:
        path: Path = self.state["dataset_path"]
        if not path.is_file():
            raise FileNotFoundError(f"Alpha158 数据不存在: {path}")
        features = tuple(self.state["train_metadata"].get("output_params", {}).get("feature_columns", ()))
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
        pred_end = self.input_params.pred_end or latest
        if pred_end > latest:
            self.logger.warning(f"pred_end={pred_end} 晚于 ETL 最新日期 {latest}; 将截断到最新日期")
            pred_end = latest
        frame = (
            pl.scan_parquet(path)
            .filter(
                (pl.col("trade_date") >= pl.lit(self.input_params.pred_start)) & (pl.col("trade_date") <= pl.lit(pred_end)),
            )
            .select(*required, *index_columns)
            .collect()
            .sort("trade_date", "ts_code")
        )
        self.report_progress(80)
        if frame.is_empty():
            raise ValueError(
                f"预测日期范围内没有数据: {self.input_params.pred_start}..{pred_end}",
            )
        if frame.select("trade_date", "ts_code").n_unique() != frame.height:
            raise ValueError("预测数据包含重复的 trade_date, ts_code")
        self.state.update(
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
        model = lgb.Booster(model_file=str(self.state["model_path"]))
        if tuple(model.feature_name()) != self.state["features"]:
            raise ValueError("模型特征名称或顺序与训练 metadata 不一致")
        self.state["model"] = model

    def predict_full_cross_section(self) -> None:
        frame: pl.DataFrame = self.state["frame"]
        matrix = feature_matrix(frame, self.state["features"])
        self.report_progress(30)
        best_iteration = self.state["train_metadata"]["output_params"]["model"]["best_iteration"]
        prediction = np.asarray(
            self.state["model"].predict(matrix, num_iteration=best_iteration),
            dtype=float,
        )
        self.report_progress(80)
        if len(prediction) != frame.height or not np.isfinite(prediction).all():
            raise FloatingPointError("模型预测数量不匹配或包含非有限值")
        self.state["predictions"] = frame.select(
            "trade_date",
            "ts_code",
            pl.Series("pred", prediction),
            pl.col("label_1d").alias("actual_return"),
            pl.col("label_1d_is_valid").alias("label_valid"),
            "name",
            "is_buyable",
            *self.state["index_columns"],
        )
        self.report_progress(95)
        self.logger.info(
            f"Full-cross-section prediction completed rows={len(prediction)} "
            f"pred_min={prediction.min():.8f} pred_max={prediction.max():.8f}",
        )

    def write_outputs(self) -> None:
        path: Path = self.state["predictions_path"]
        atomic_write(
            path,
            lambda temporary: self.state["predictions"].write_parquet(temporary, compression="zstd"),
        )
        self.report_progress(95)
        self.logger.info(
            f"Predictions written path={path} rows={self.state['predictions'].height} bytes={path.stat().st_size}",
        )

    def build_output_params(self) -> LgbmPredictOutputParams:
        output_dir: Path = self.task_dir
        predictions: pl.DataFrame = self.state["predictions"]
        prediction_record = artifact_record(self.state["predictions_path"], output_dir)
        model_target = self.state["train_metadata"]["output_params"]["protocol"]["label_column"]
        scores = predictions["pred"].to_numpy()
        buyable = predictions["is_buyable"]
        valid = predictions["label_valid"]
        index_columns = list(self.state["index_columns"])
        index_statistics = {}
        for column in index_columns:
            weights = predictions[column]
            index_statistics[column] = {
                "constituents": predictions.filter(pl.col(column) > 0)["ts_code"].n_unique(),
                "days_with_weights": predictions.filter(pl.col(column).is_not_null())["trade_date"].n_unique(),
                "null_rows": weights.null_count(),
            }
        return self.output_cls(
            protocol={
                "train_end_exclusive": self.state["train_end"],
                "pred_start_inclusive": self.input_params.pred_start,
                "pred_end_inclusive": self.state["actual_pred_end"],
                "cross_section_filter": "none",
                "execution_filter": "deferred to backtest via is_buyable",
                "actual_return_column": "label_1d",
                "actual_return_unit": "decimal",
                "prediction_score": "model output trained on cross-sectional return rank; not a return or probability",
                "row_key": ["trade_date", "ts_code"],
                "index_weight_unit": "decimal",
            },
            rows=predictions.height,
            date_range={
                "start": predictions["trade_date"].min(),
                "end": predictions["trade_date"].max(),
            },
            output_columns=predictions.columns,
            statistics={
                "days": predictions["trade_date"].n_unique(),
                "symbols": predictions["ts_code"].n_unique(),
                "pred": {
                    "mean": float(np.mean(scores)),
                    "min": float(np.min(scores)),
                    "median": float(np.median(scores)),
                    "max": float(np.max(scores)),
                },
                "buyable_rows": int(buyable.sum()),
                "valid_return_rows": int(valid.sum()),
                "candidate_rows": predictions.filter(pl.col("is_buyable") & pl.col("label_valid")).height,
                "indices": index_statistics,
            },
            model_target=model_target,
            index_weight_columns=index_columns,
            artifacts={
                "predictions": prediction_record,
            },
            predictions_file=str(self.state["predictions_path"]),
        )
