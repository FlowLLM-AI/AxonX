"""Portable, immutable online publications and revision history."""

from datetime import date
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from ...enums import TaskType
from .artifact import ArtifactRecord
from .protocol import STOCK_SIGNALS_FORMAT, Protocol, validate_protocol


class OnlineCommit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    commit_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    task_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    trade_date: str = Field(pattern=r"^\d{8}$")
    trade_time: str = Field(pattern=r"^\d{4}$")
    revision: int = Field(ge=1)
    committed_at: AwareDatetime
    model_identity: dict[str, str] = Field(min_length=1)
    protocol: dict[str, Any]
    artifacts: dict[str, ArtifactRecord] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_commit(self):
        validate_protocol(self.protocol, TaskType.INFERENCE)
        if "targets" in self.artifacts or (
            "signals" in self.artifacts
            and self.protocol.get("report", {}).get("signals_format") != STOCK_SIGNALS_FORMAT
        ):
            raise ValueError("Unsupported stock signals format; regenerate online records with a new task_name")
        date(
            int(self.trade_date[:4]),
            int(self.trade_date[4:6]),
            int(self.trade_date[6:]),
        )
        if int(self.trade_time[:2]) > 23 or int(self.trade_time[2:]) > 59:
            raise ValueError("Invalid online signal time")
        return self


class OnlineHistory(Protocol):
    task_type: Literal[TaskType.INFERENCE] = TaskType.INFERENCE
    kind: Literal["online_history"] = "online_history"
    strategy_identity: str = Field(pattern=r"^[0-9a-f]{64}$")
    commits: list[OnlineCommit] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_commits(self):
        identities = [item.commit_id for item in self.commits]
        if len(identities) != len(set(identities)):
            raise ValueError("Duplicate online commit")
        if len({c.task_id for c in self.commits}) > 1:
            raise ValueError("Online history must belong to one Task")
        if any(
            c.protocol.get("report", {}).get("strategy_identity", self.strategy_identity) != self.strategy_identity
            for c in self.commits
        ):
            raise ValueError("Online commit strategy differs from its history")
        revisions: dict[tuple[str, str], int] = {}
        for item in self.commits:
            key = (item.trade_date, item.trade_time)
            revisions[key] = revisions.get(key, 0) + 1
            if item.revision != revisions[key]:
                raise ValueError("Online revisions must be consecutive")
        return self

    def active(self, as_of: str | None = None) -> list[OnlineCommit]:
        """Last revision wins; later reports require replay after a historical revision."""
        latest = {(item.trade_date, item.trade_time): item for item in self.commits}
        return [latest[key] for key in sorted(latest) if as_of is None or key[0] <= as_of]

    def report_is_current(self, commit: OnlineCommit) -> bool:
        index = next(
            (i for i, item in enumerate(self.commits) if item.commit_id == commit.commit_id),
            None,
        )
        return index is not None and not any(
            (item.trade_date, item.trade_time) <= (commit.trade_date, commit.trade_time)
            for item in self.commits[index + 1 :]
        )
