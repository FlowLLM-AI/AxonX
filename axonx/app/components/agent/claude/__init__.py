"""Claude Code Agent implementation and supporting modules.

backend: Interactive SDK client lifecycle, reply streams and session operations.
projector: Stable message blocks and incremental presentation patches.
session_store: Adaptation of the AxonX transcript store to Claude SDK sessions.
tools: In-process MCP tools exposing application Jobs.
"""

from . import backend, projector, session_store, tools
from .backend import ClaudeAgentComponent

__all__ = [
    "ClaudeAgentComponent",
    "backend",
    "projector",
    "session_store",
    "tools",
]
