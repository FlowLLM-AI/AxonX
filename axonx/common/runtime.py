"""Shared process workspace, logging and environment settings."""

from pydantic import BaseModel, ConfigDict, Field

from .constants import AXONX_DEFAULT_LOG_DIR, AXONX_DEFAULT_TIMEZONE

AXONX_TASK_WORKSPACE_DIR = "AXONX_TASK_WORKSPACE_DIR"
AXONX_TASK_LOG_DIR = "AXONX_TASK_LOG_DIR"
AXONX_TASK_TIMEZONE = "AXONX_TASK_TIMEZONE"


class RuntimeSettings(BaseModel):
    """Settings shared by process workspaces and execution environments."""

    model_config = ConfigDict(extra="ignore")
    workspace_dir: str = ".axonx"
    log_dir: str = AXONX_DEFAULT_LOG_DIR
    timezone: str = AXONX_DEFAULT_TIMEZONE
    environment: dict[str, str] = Field(default_factory=dict)
