"""Factor-aware Alpha158 training reuses the baseline model lifecycle."""

from pydantic import Field, field_validator
from axonx_alpha158.train import (
    LgbmTrainInputParams as BaseTrainInput,
    LgbmTrainOutputParams,
    LgbmTrainTask as BaseTrainTask,
    MODEL_LABELS,
)

from .internal.cross_section import CONTEXT_FEATURES, selected_features

__all__ = ["LgbmTrainInputParams", "LgbmTrainOutputParams", "LgbmTrainTask", "MODEL_LABELS"]


class LgbmTrainInputParams(BaseTrainInput):
    context_groups: str = Field(
        default="market,liquidity,interaction",
        description="Comma-separated context groups, or none for baseline.",
    )

    @field_validator("context_groups")
    @classmethod
    def validate_context_groups(cls, value: str) -> str:
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
        requested = selected_features(self.input_params.context_groups)
        if missing := set(requested) - set(features):
            raise ValueError(f"ETL missing requested context features: {sorted(missing)}")
        return tuple(name for name in features if name not in CONTEXT_FEATURES or name in requested)

    def build_output_params(self) -> LgbmTrainOutputParams:
        output = super().build_output_params()
        output.protocol["context_groups"] = self.input_params.context_groups
        return output
