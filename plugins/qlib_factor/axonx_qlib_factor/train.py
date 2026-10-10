"""Factor-aware Alpha158 training reuses the baseline model lifecycle."""

from pydantic import Field, field_validator
from axonx_qlib_a158.train import (
    LgbmTrainInputParams as BaseTrainInput,
    LgbmTrainOutputParams,
    LgbmTrainTask as BaseTrainTask,
    MODEL_LABELS,
)

from .internal.cross_section import CONTEXT_FEATURES, PREFIX, WINDOWS, selected_features

__all__ = ["LgbmTrainInputParams", "LgbmTrainOutputParams", "LgbmTrainTask", "MODEL_LABELS"]


class LgbmTrainInputParams(BaseTrainInput):
    context_groups: str = Field(
        default="none",
        description="Optional comma-separated context groups; default none uses the 158 base features.",
    )

    context_windows: list[int] = Field(
        default_factory=lambda: list(WINDOWS),
        min_length=1,
        description=(
            "Global mean/variance horizons; nonempty subset of 1,3,5,10 trading days. "
            "Stock groups use fixed horizons."
        ),
    )

    @field_validator("context_windows")
    @classmethod
    def validate_context_windows(cls, value: list[int]) -> list[int]:
        if set(value) - set(WINDOWS):
            raise ValueError(f"context_windows must be selected from {WINDOWS}")
        return [window for window in WINDOWS if window in value]

    @field_validator("context_groups", mode="before")
    @classmethod
    def validate_context_groups(cls, value: object) -> object:
        # CLI null tokens (none/null) select the documented no-context control.
        if value is None:
            value = "none"
        if isinstance(value, str):
            selected_features(value)
        return value


class LgbmTrainTask(BaseTrainTask):
    """Train the selected factor groups with the Alpha158 temporal model lifecycle.

    Reads the upstream ETL dataset, selects boosting rounds on the training-period
    validation tail, and refits before the exclusive cutoff. Writes the model,
    selected feature order, validation history and feature importance artifacts.
    """

    input_cls = LgbmTrainInputParams
    input_params: LgbmTrainInputParams

    def select_features(self, features: tuple[str, ...]) -> tuple[str, ...]:
        requested = selected_features(self.input_params.context_groups, tuple(self.input_params.context_windows))
        if missing := set(requested) - set(features):
            raise ValueError(f"ETL missing requested context features: {sorted(missing)}")
        if unknown := {name for name in features if name.startswith(PREFIX)} - set(CONTEXT_FEATURES):
            raise ValueError(f"ETL has unsupported context features: {sorted(unknown)}; rerun current ETL")
        return tuple(name for name in features if not name.startswith(PREFIX) or name in requested)

    def build_output_params(self) -> LgbmTrainOutputParams:
        output = super().build_output_params()
        output.protocol["context_groups"] = self.input_params.context_groups
        output.protocol["context_windows"] = self.input_params.context_windows
        return output
