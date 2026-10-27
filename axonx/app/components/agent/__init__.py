"""Agent backends and their shared session and event contracts.

base: Backend-neutral Agent component contract.
claude: Claude Code Agent implementation and supporting modules.
models: Agent presentation models and backend-neutral session storage records.
session_store: Local JSONL transcripts, atomic summaries and per-session disk operations.
"""

from . import base, claude, models, session_store

__all__ = [
    "base",
    "claude",
    "models",
    "session_store",
]
