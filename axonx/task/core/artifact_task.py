"""Task base for artifacts stored in a task-specific directory."""

from abc import ABC
from datetime import datetime
from pathlib import Path

from ...constants import AXONX_DEFAULT_TIMEZONE
from ..base import BaseInputParams, BaseOutputParams, BaseTask, TaskMetadata
from .artifact_store import ArtifactStore


class BaseArtifactTask(BaseTask, ABC):
    """Persist task output metadata beside its artifacts."""

    def __init__(
        self,
        input_params: BaseInputParams | dict,
        *,
        workspace_path: str | Path,
        reg_name: str | None = None,
        timezone: str = AXONX_DEFAULT_TIMEZONE,
    ) -> None:
        super().__init__(input_params, workspace_path=workspace_path, reg_name=reg_name, timezone=timezone)
        self.artifact_store = ArtifactStore(self.workspace_path)

    @staticmethod
    def normalize_yyyymmdd(value: object, *, optional: bool = False) -> str | None:
        """Normalize a compact calendar date."""
        if optional and (value is None or isinstance(value, str) and value.lower() in {"", "none"}):
            return None
        normalized = str(value)
        try:
            parsed = datetime.strptime(normalized, "%Y%m%d")
        except ValueError as exc:
            raise ValueError(f"必须是有效 YYYYMMDD: {normalized}") from exc
        if parsed.strftime("%Y%m%d") != normalized:
            raise ValueError(f"必须是有效 YYYYMMDD: {normalized}")
        return normalized

    @property
    def task_dir(self) -> Path:
        return self.artifact_store.task_directory(self.task_type.value, self.task_id)

    @property
    def metadata_path(self) -> Path:
        return self.task_dir / "metadata.json"

    def prepare_output(self) -> BaseOutputParams:
        output_params = super().prepare_output()
        task_metadata = TaskMetadata(
            task_id=self.task_id,
            reg_name=self.reg_name,
            created_at=self.created_at,
            task_type=self.task_type,
            input_params=self.input_params,
            output_params=output_params,
        )
        self.artifact_store.write_metadata(self.metadata_path, task_metadata)
        return output_params
