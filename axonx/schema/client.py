"""Validated options shared by every HTTP client construction path."""

from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, PositiveFloat, field_validator

from ..constants import AXONX_DEFAULT_REQUEST_TIMEOUT


class HttpClientOptions(BaseModel):
    """Connection settings for an AxonX HTTP client."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    url: str | None = None
    timeout: PositiveFloat = AXONX_DEFAULT_REQUEST_TIMEOUT

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        """Normalize and validate an optional absolute HTTP(S) base URL."""
        if value is None:
            return None
        value = value.rstrip("/")
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("url must be an absolute HTTP(S) URL")
        return value
