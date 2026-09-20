"""Validated contracts returned by workspace services."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class WorkspaceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FileCopy(WorkspaceModel):
    """Public description of a file staged through the HTTP protocol."""

    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size: int = Field(ge=0)


class StagedFile(FileCopy):
    """A staged copy together with its server-local absolute location."""

    location: str = Field(min_length=1)


class WorkspaceEntry(WorkspaceModel):
    name: str
    path: str
    kind: Literal["directory", "file", "symlink"]
    preview_kind: str | None = None
    supported: bool = False
    size: int | None = Field(default=None, ge=0)
    modified_at: float = 0.0


class WorkspaceListing(WorkspaceModel):
    path: str
    entries: list[WorkspaceEntry] = Field(default_factory=list)
    truncated: bool = False


class DeletedEntry(WorkspaceModel):
    deleted: str
    kind: Literal["directory", "file"]


class PreviewBase(WorkspaceModel):
    kind: str
    size: int = Field(ge=0)


class UnsupportedPreview(PreviewBase):
    kind: Literal["unsupported"] = "unsupported"


class TextPreview(PreviewBase):
    kind: Literal["text"] = "text"
    content: str
    truncated: bool = False


class MarkdownPreview(PreviewBase):
    kind: Literal["markdown"] = "markdown"
    content: str
    frontmatter: Any = None
    frontmatter_error: str | None = None
    truncated: bool = False


class StructuredPreview(PreviewBase):
    kind: Literal["json", "yaml"]
    content: str = ""
    data: Any = None
    parse_error: str | None = None
    truncated: bool = False


class CsvPreview(PreviewBase):
    kind: Literal["csv"] = "csv"
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1)
    has_more: bool = False


class ParquetColumn(WorkspaceModel):
    name: str
    type: str
    nullable: bool


class ParquetPreview(PreviewBase):
    kind: Literal["parquet"] = "parquet"
    columns: list[str] = Field(default_factory=list)
    column_schema: list[ParquetColumn] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1)
    has_more: bool = False
    row_count: int = Field(ge=0)
    row_group_count: int = Field(ge=0)


FilePreview = (
    UnsupportedPreview
    | TextPreview
    | MarkdownPreview
    | StructuredPreview
    | CsvPreview
    | ParquetPreview
)
