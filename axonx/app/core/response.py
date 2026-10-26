"""Callbacks committed after the enclosing response finishes sending."""

from collections.abc import Callable
from contextvars import ContextVar

RESPONSE_CALLBACKS: ContextVar[list[Callable[[], None]] | None] = ContextVar("response_callbacks", default=None)
