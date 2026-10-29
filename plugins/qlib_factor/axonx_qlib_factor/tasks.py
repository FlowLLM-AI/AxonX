"""Factor ETL and feature-selecting training on the shared Alpha158 lifecycle."""

from collections.abc import Iterable

from pydantic import Field, field_validator

from axonx.task.core.base import TaskStep
from axonx.task.models.artifacts import ArtifactRecord
from axonx.task.storage.artifacts import artifact_record
from axonx.task.storage.files import atomic_write
from axonx_qlib_a158.etl import Alpha158OutputParams, Alpha158Task
from axonx_qlib_a158.train import LgbmTrainInputParams, LgbmTrainTask

from .features import (
    BETA_WINDOW,
    CONTEXT_FEATURES,
    FEATURE_GROUPS,
    PREFIX,
    RISK_WINDOW,
    WINDOWS,
    ContextGroup,
    ContextWindow,
    calculate_context,
    context_protocol,
    selected_features,
)


class FactorETLTask(Alpha158Task):
    """Publish Alpha158 plus causal context features and daily market diagnostics."""

    extra_features = CONTEXT_FEATURES
    # The oldest residual in the risk window needs its own prior beta history.
    lookback_days = BETA_WINDOW + RISK_WINDOW

    def additional_feature_steps(self) -> Iterable[TaskStep]:
        yield self.calculate_cross_section_context

    def calculate_cross_section_context(self) -> None:
        features, daily = calculate_context(self.state["frame"])
        self.state["frame"] = self.state["frame"].join(
            features, on=["trade_date", "ts_code"], how="left", maintain_order="left"
        )
        self.state["context_daily"] = daily
        self.report_progress(95)
        self.logger.info(f"Context calculated features={len(CONTEXT_FEATURES)} days={daily.height}")

    def write_outputs(self) -> None:
        super().write_outputs()
        path = self.task_dir / "context_daily.parquet"
        atomic_write(path, lambda temporary: self.state["context_daily"].write_parquet(temporary, compression="zstd"))
        self.state["context_path"] = path

    def build_output_params(self) -> Alpha158OutputParams:
        output = super().build_output_params()
        output.protocol["feature_family"] = "qlib_factor"
        output.protocol["feature_rules"]["context"] = context_protocol()
        output.protocol["qlib_deviations"][
            "features"
        ] += f" Adds {len(CONTEXT_FEATURES)} causal market-moment and stock-risk features."
        output.artifacts["context_daily"] = ArtifactRecord(**artifact_record(self.state["context_path"], self.task_dir))
        output.feature_schema["groups"] = [
            *[{"name": name, "features": list(columns)} for name, columns in FEATURE_GROUPS.items()],
            *output.feature_schema["groups"],
        ]
        return output


class FactorTrainInputParams(LgbmTrainInputParams):
    context_groups: list[ContextGroup] = Field(
        default_factory=list,
        description="Optional context groups; an empty list uses the 158 base features.",
    )
    context_windows: list[ContextWindow] = Field(
        default_factory=lambda: list(WINDOWS),
        min_length=1,
        description="Global mean/variance horizons: nonempty subset of 1,3,5,10. Stock groups use fixed horizons.",
    )

    @field_validator("context_groups")
    @classmethod
    def normalize_groups(cls, values: list[ContextGroup]) -> list[ContextGroup]:
        return [name for name in FEATURE_GROUPS if name in values]

    @field_validator("context_windows")
    @classmethod
    def normalize_windows(cls, values: list[ContextWindow]) -> list[ContextWindow]:
        return [window for window in WINDOWS if window in values]


class FactorTrainTask(LgbmTrainTask):
    """Select optional factor groups and reuse cutoff-safe LightGBM training."""

    input_cls = FactorTrainInputParams
    input_params: FactorTrainInputParams

    def select_features(self, features: tuple[str, ...]) -> tuple[str, ...]:
        requested = selected_features(self.input_params.context_groups, self.input_params.context_windows)
        if missing := set(requested) - set(features):
            raise ValueError(f"ETL missing requested context features: {sorted(missing)}")
        if unknown := {name for name in features if name.startswith(PREFIX)} - set(CONTEXT_FEATURES):
            raise ValueError(f"ETL has unsupported context features: {sorted(unknown)}")
        return tuple(name for name in features if not name.startswith(PREFIX) or name in requested)

    def additional_training_protocol(self) -> dict:
        return {
            "context_groups": self.input_params.context_groups,
            "context_windows": self.input_params.context_windows,
        }
