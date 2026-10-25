"""CLI connection and output options."""

from typing import Literal

from ..common.connection import ConnectionOptions


class ClientOptions(ConnectionOptions):
    stream: bool = False
    stream_format: Literal["blocks", "json"] = "blocks"
