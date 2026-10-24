"""Prediction comparison is a report, independent of factor analysis rows/scores."""

from abc import abstractmethod
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..enums import TaskType
from ..schemas.artifact import ArtifactRecord
from ..core import BaseInputParams, BaseOutputParams, BaseTask


class PredictionComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    status: Literal["consistent", "different", "protocol_mismatch", "missing", "error"]
    reason: str = ""
    metrics: dict[str, Any] = Field(default_factory=dict)
    artifacts: dict[str, ArtifactRecord] = Field(default_factory=dict)


class BasePredictionCompareInputParams(BaseInputParams):
    comparison_keys: list[str] = Field(min_length=1)

    @field_validator("comparison_keys")
    @classmethod
    def unique_keys(cls, keys: list[str]) -> list[str]:
        if any(not key for key in keys) or len(keys) != len(set(keys)):
            raise ValueError("comparison keys must be nonempty and unique")
        return keys


class BasePredictionCompareOutputParams(BaseOutputParams):
    comparisons: list[PredictionComparison] = Field(default_factory=list)


class BasePredictionCompareTask(BaseTask):
    comparisons: list[PredictionComparison]
    task_type = TaskType.ANALYSIS
    report_kind = "online"
    input_cls = BasePredictionCompareInputParams
    output_cls = BasePredictionCompareOutputParams

    @abstractmethod
    def compare(self, key: str) -> PredictionComparison:
        """Compare protocol, candidates, scores and ranks; missing inputs are a report outcome."""

    def build_task_steps(self):
        yield self.compare_predictions

    def compare_predictions(self) -> None:
        self.comparisons: list[PredictionComparison] = []
        for key in self.input_params.comparison_keys:
            try:
                result = self.compare(key)
                if result.key != key:
                    raise ValueError("Comparison result key does not match request")
            except Exception as exc:
                result = PredictionComparison(key=key, status="error", reason=f"{type(exc).__name__}: {exc}")
            self.comparisons.append(result)
            self.metadata.output_params["comparisons"] = [item.model_dump(mode="json") for item in self.comparisons]
            self.persist_metadata()

    def build_output_params(self) -> BasePredictionCompareOutputParams:
        return self.output_cls(comparisons=self.comparisons)
