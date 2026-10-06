"""Job execution contracts and built-in implementations."""

from .base import BaseJob
from .contracts import JobCatalog, JobInfo, JobResponse
from .events import (
    JOB_EVENT_ADAPTER,
    AgentBlockPatch,
    AgentMessageEvent,
    ArtifactEvent,
    JobEvent,
    LogEvent,
    ProgressEvent,
    ResultEvent,
    fold_events,
)
from .context import RuntimeContext
from .pipeline import PipelineJob
from .managed import ManagedTaskJob, TaskStageError
from .batch import TaskBatchJob

__all__ = [
    "ArtifactEvent",
    "AgentBlockPatch",
    "AgentMessageEvent",
    "BaseJob",
    "JOB_EVENT_ADAPTER",
    "JobCatalog",
    "JobEvent",
    "JobInfo",
    "JobResponse",
    "LogEvent",
    "PipelineJob",
    "ManagedTaskJob",
    "TaskStageError",
    "TaskBatchJob",
    "ProgressEvent",
    "ResultEvent",
    "RuntimeContext",
    "fold_events",
]
