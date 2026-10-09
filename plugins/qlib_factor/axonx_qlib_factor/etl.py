"""Extend Alpha158 ETL with causal cross-sectional context features."""

from collections.abc import Callable, Iterable

import polars as pl
from axonx_qlib_a158.etl import (
    Alpha158InputParams,
    Alpha158OutputParams as BaseOutputParams,
    Alpha158Task as BaseTask,
)
from axonx_qlib_a158.internal.etl_pipeline import FEATURES
from axonx_qlib_a158.internal.features import dataset_statistics

from axonx.task.core import TaskStep
from axonx.task.storage import artifact_record
from axonx.utils.fs import atomic_write

from .internal.cross_section import CONTEXT_FEATURES, FEATURE_GROUPS, calculate_context, context_protocol

__all__ = ["Alpha158InputParams", "Alpha158OutputParams", "Alpha158Task"]


class Alpha158OutputParams(BaseOutputParams):
    context_daily_file: str
    context: dict


class Alpha158Task(BaseTask):
    """Build Alpha158 features and causal daily context from workspace market data.

    Extends the baseline ETL with 26 context factors while preserving its stock,
    label and calendar artifacts. Writes the complete feature schema, feature
    statistics and daily context diagnostics for downstream model experiments.
    """

    output_cls = Alpha158OutputParams
    extra_features = CONTEXT_FEATURES

    def additional_feature_steps(self) -> Iterable[TaskStep]:
        yield self.calculate_cross_section_context

    def calculate_cross_section_context(self) -> None:
        """Attach causal market, amount-group, relative, and interaction features."""
        features, daily = calculate_context(self.state["frame"])
        self.state["frame"] = self.state["frame"].join(
            features, on=["trade_date", "ts_code"], how="left", maintain_order="left"
        )
        self.state["context_daily"] = daily
        self.report_progress(95)
        self.logger.info(f"Context calculated features={len(CONTEXT_FEATURES)} days={daily.height}")

    @staticmethod
    def _statistics(output: pl.DataFrame, *, progress: Callable[[float], None] | None = None) -> pl.DataFrame:
        return dataset_statistics(output, progress=progress, columns=(*FEATURES, *CONTEXT_FEATURES))

    def write_outputs(self) -> None:
        super().write_outputs()
        path = self.task_dir / "context_daily.parquet"
        atomic_write(path, lambda temporary: self.state["context_daily"].write_parquet(temporary, compression="zstd"))
        self.state["context_path"] = path

    def additional_output_params(self) -> dict:
        path = self.state["context_path"]
        return {"context_daily_file": str(path), "context": context_protocol()}

    def build_output_params(self) -> Alpha158OutputParams:
        output = super().build_output_params()
        output.protocol["qlib_deviations"][
            "features"
        ] += " Adds 26 causal market, liquidity, relative and interaction context features."
        output.artifacts["context_daily"] = artifact_record(self.state["context_path"], self.task_dir)
        output.feature_schema["groups"] = [
            *[{"name": name, "features": list(columns)} for name, columns in FEATURE_GROUPS.items()],
            *output.feature_schema["groups"],
        ]
        return output
