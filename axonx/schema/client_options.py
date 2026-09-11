"""Validated options shared by client construction paths."""

from pydantic import BaseModel, ConfigDict, Field, PositiveFloat, model_validator

from ..constants import AXONX_DEFAULT_REQUEST_TIMEOUT


class ClientOptions(BaseModel):
    """Connection settings for an AxonX client."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    host_ip: str | None = Field(default=None, min_length=1)
    host_port: int | None = Field(default=None, ge=1, le=65535)
    timeout: PositiveFloat = AXONX_DEFAULT_REQUEST_TIMEOUT

    @model_validator(mode="after")
    def validate_address(self):
        """Require host and port together, or neither for automatic discovery."""
        if (self.host_ip is None) != (self.host_port is None):
            raise ValueError("host_ip and host_port must be provided together")
        return self
