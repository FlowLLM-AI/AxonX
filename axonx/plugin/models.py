"""Plugin metadata shared by discovery, wheel inspection and the CLI."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class PluginInfo(BaseModel):
    """Metadata and fingerprints of a plugin distribution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    distribution: str
    version: str
    plugins: list[str] = Field(default_factory=list)
    tasks: dict[str, str] = Field(default_factory=dict)
    requirements: list[str] = Field(default_factory=list)
    content_sha256: str | None = None
    sha256: str | None = None
    error: str | None = None


class PluginArtifact(PluginInfo):
    """A validated wheel with required archive and content fingerprints."""

    wheel: Path
    content_sha256: str
    sha256: str
