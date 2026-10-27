"""Claude Code Agent implementation and supporting modules.

backend: Configure and run Claude sessions, serialize turns and own SDK client cleanup.
projector: Convert Claude messages, results and history into public events and display blocks.
session_store: Extend local storage with Claude SDK summary folding under one session lock.
tools: Adapt resolved AxonX Jobs to in-process MCP schemas and dispatcher-backed handlers.
"""

from . import backend, projector, session_store, tools

__all__ = [
    "backend",
    "projector",
    "session_store",
    "tools",
]
