"""CLI connection and output options."""

from typing import Literal

from ..app.connection import ConnectionOptions


class ClientOptions(ConnectionOptions):
    stream: bool = False
    stream_format: Literal["blocks", "json"] = "blocks"
