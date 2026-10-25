"""Domain execution and shared operations."""

from __future__ import annotations

from abc import abstractmethod

from .task import BaseTask
from ..task_enums import TaskType
from ..models.params import (
    BasePredictionCompareInputParams,
    BasePredictionCompareOutputParams,
    PredictionComparison,
)


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
