"""Application update admission and status.

base: Component-facing update contract and synchronous host backend protocol.
local: Local update admission and response-completion handoff to the host.
"""

from . import base, local

__all__ = [
    "base",
    "local",
]
