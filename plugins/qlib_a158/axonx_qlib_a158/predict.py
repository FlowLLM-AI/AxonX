"""Run full-cross-section prediction from an Alpha158 LightGBM training task."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Self

import numpy as np
import polars as pl
from pydantic import Field, model_validator

from axonx.task.builtins.stock.data import KEYS, validate_keys
from axonx.task.core.base import TaskStep
from axonx.task.core.research import BasePredictTask
from axonx.task.models.artifacts import fingerprint, prediction_protocol
from axonx.task.models.base import DateString
from axonx.task.models.identity import (
    TaskType,
    task_type_from_id,
    validate_upstream_task_ids,
)
from axonx.task.models.params import BaseInputParams, BasePredictOutputParams, BaseTrainOutputParams
from axonx.task.storage.artifacts import artifact_record
from axonx.task.storage.files import atomic_write
from axonx.task.storage.inputs import (
    read_upstream_metadata,
    upstream_artifact,
    upstream_artifacts,
)

from .internal.modeling import feature_contract, feature_identity, feature_matrix, load_lightgbm


class LgbmPredictOutputParams(BasePredictOutputParams):
    model_target: str
    index_weight_columns: list[str]


class LgbmPredictInputParams(BaseInputParams):
    """Configure an out-of-sample prediction interval for a training task."""

    pred_start: DateString = Field(
        default="20230101",
        description="First prediction date in YYYYMMDD format; must follow the training period.",
    )
    pred_end: DateString | None = Field(
        default=None,
        description="Last prediction date in YYYYMMDD format; omit for the latest dataset date.",
    )

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
        yield self.resolve_upstream_dataset
        yield self.load_and_validate_prediction_data
        yield self.load_model
        yield self.predict_full_cross_section
        yield self.write_outputs

    def resolve_train_task(self) -> None:
        train_task_id = self.input_params.upstream_task_id(TaskType.TRAIN)
        _, train_metadata = read_upstream_metadata(self.workspace_path, train_task_id)
        collection = BaseTrainOutputParams.model_validate(train_metadata["output_params"])
        selected = collection.select_models(self.input_params.pred_start)
        if len(selected) != 1:
            raise ValueError("LightGBM prediction requires one active model")
        member_name, member = next(iter(selected.items()))
        self.state["member_name"] = member_name
        self.state["member"] = member.model_dump(mode="json")
        self.state["model_collection"] = collection.model_dump(mode="json")
        model_path = upstream_artifact(self, train_task_id, member.model_artifact)[0]
        train_end = member.train_end_exclusive
        if self.input_params.pred_start < train_end:
            raise ValueError("Prediction precedes the training cutoff")
        output_dir = self.task_dir
        self.state.update(
            train_metadata=train_metadata,
            model_path=model_path,
            predictions_path=output_dir / "predictions.parquet",
        )
        self.logger.info(
            f"Prediction training source resolved train_task_id={train_task_id} "
            f"model={model_path} train_end={train_end}",
        )

    def resolve_upstream_dataset(self) -> None:
        upstream_ids = validate_upstream_task_ids(
            self.state["train_metadata"].get("input_params", {}).get("upstream_task_ids", [])
        )
        explicit = [
            task_id for task_id in self.input_params.upstream_task_ids if task_type_from_id(task_id) == TaskType.ETL
        ]
        etl_upstream_ids = explicit or [
            task_id for task_id in upstream_ids if task_type_from_id(task_id) == TaskType.ETL
        ]
        if len(etl_upstream_ids) != 1:
            raise ValueError("训练 metadata 必须包含一个 ETL 上游任务")
        etl_task_id = etl_upstream_ids[0]
        _, etl_metadata = read_upstream_metadata(self.workspace_path, etl_task_id)
        feature_protocol = etl_metadata["output_params"]["protocol"]
        if feature_identity(feature_protocol) != feature_identity(self.state["model_collection"]["feature_protocol"]):
            raise ValueError("Feature protocol differs from training")
        (dataset_path,) = upstream_artifacts(self, etl_task_id, "dataset", metadata=etl_metadata)
        self.state.update(
            etl_task_id=etl_task_id,
            feature_protocol=feature_contract(feature_protocol),
            dataset_path=dataset_path,
        )
        self.logger.info(f"Prediction dataset resolved etl_task_id={etl_task_id} dataset={dataset_path}")

    def load_and_validate_prediction_data(self) -> None:
        path: Path = self.state["dataset_path"]
        features = tuple(self.state["member"]["model"]["feature_names"])
        if not features:
            raise ValueError("训练 metadata 缺少 feature_columns")
        schema = pl.read_parquet_schema(path)
        self.report_progress(10)
        index_columns = tuple(column for column in schema if column.startswith("index_weight_"))
        required = (
            "trade_date",
            "trade_time",
            "ts_code",
            "name",
            "is_buyable_at_signal",
            "is_model_candidate",
            "signal_price",
            "signal_adjustment_factor",
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
                (pl.col("trade_date") >= pl.lit(self.input_params.pred_start))
                & (pl.col("trade_date") <= pl.lit(pred_end)),
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
        use_to = self.state["member"]["use_to"]
        if use_to is not None and frame["trade_date"].max() >= use_to:
            raise ValueError("Prediction interval exceeds the selected model's use window")
        validate_keys(frame)
        self.state.update(
            frame=frame,
            features=features,
            index_columns=index_columns,
        )
        self.report_progress(95)
        self.logger.info(
            f"Prediction data loaded rows={frame.height} dates={frame['trade_date'].n_unique()} "
            f"start={frame['trade_date'].min()} end={frame['trade_date'].max()}",
        )

    def load_model(self) -> None:
        lgb = load_lightgbm()
        model = lgb.Booster(model_file=str(self.state["model_path"]))
        if tuple(model.feature_name()) != self.state["features"]:
            raise ValueError("模型特征名称或顺序与训练 metadata 不一致")
        self.state["model"] = model

    def predict_full_cross_section(self) -> None:
        frame: pl.DataFrame = self.state["frame"]
        matrix = feature_matrix(frame, self.state["features"])
        self.report_progress(30)
        best_iteration = self.state["member"]["model"]["best_iteration"]
        prediction = np.asarray(
            self.state["model"].predict(matrix, num_iteration=best_iteration),
            dtype=float,
        )
        self.report_progress(80)
        if len(prediction) != frame.height or not np.isfinite(prediction).all():
            raise FloatingPointError("模型预测数量不匹配或包含非有限值")
        self.state["predictions"] = (
            frame.select(
                "trade_date",
                "trade_time",
                "ts_code",
                "name",
                pl.Series("pred", prediction),
                "is_buyable_at_signal",
                "is_model_candidate",
                "signal_price",
                "signal_adjustment_factor",
                *self.state["index_columns"],
            )
            .sort(
                ["trade_date", "trade_time", "pred", "ts_code"],
                descending=[False, False, True, False],
            )
            .with_columns(
                pl.int_range(1, pl.len() + 1).over(list(KEYS[:2])).alias("rank"),
                pl.when(pl.col("is_buyable_at_signal"))
                .then(pl.col("is_buyable_at_signal").cast(pl.Int64).cum_sum().over(list(KEYS[:2])))
                .alias("buyable_rank"),
            )
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
        frame = self.state["predictions"]
        member_name = self.state["member_name"]
        model_revision = self.state["model_collection"]["artifacts"][self.state["member"]["model_artifact"]]["revision"]
        return self.output_cls(
            rows=frame.height,
            date_range={
                "start": frame["trade_date"].min(),
                "end": frame["trade_date"].max(),
            },
            output_columns=frame.columns,
            statistics={
                "days": frame["trade_date"].n_unique(),
                "symbols": frame["ts_code"].n_unique(),
                "pred": {
                    "mean": frame["pred"].mean(),
                    "min": frame["pred"].min(),
                    "median": frame["pred"].median(),
                    "max": frame["pred"].max(),
                },
                "buyable_rows": frame.filter("is_buyable_at_signal").height,
                "candidate_rows": frame.filter(pl.col("is_model_candidate") & pl.col("is_buyable_at_signal")).height,
                "indices": {
                    column: {
                        "constituents": frame.filter(pl.col(column) > 0)["ts_code"].n_unique(),
                        "days_with_weights": frame.filter(pl.col(column).is_not_null())["trade_date"].n_unique(),
                        "null_rows": frame[column].null_count(),
                    }
                    for column in self.state["index_columns"]
                },
            },
            model_target=self.state["model_collection"]["training_target"]["label_column"],
            index_weight_columns=list(self.state["index_columns"]),
            protocol=prediction_protocol(
                TaskType.PREDICT,
                {"model": "pred"},
                windows=[
                    {
                        "prediction_start": self.input_params.pred_start,
                        "prediction_end_exclusive": (
                            datetime.strptime(frame["trade_date"].max(), "%Y%m%d") + timedelta(days=1)
                        ).strftime("%Y%m%d"),
                        "models": {"model": member_name},
                        "model_identity": {
                            "models_sha256": fingerprint({member_name: model_revision}),
                            "features_sha256": feature_identity(self.state["feature_protocol"]),
                            "family": self.state["feature_protocol"]["feature_family"],
                            "trade_time": "1500",
                            "return_unit": "decimal",
                        },
                    }
                ],
                market_upstream_task_id=self.state["etl_task_id"],
            ),
            artifacts={"predictions": artifact_record(self.state["predictions_path"], self.task_dir)},
        )
