"""Agent backends and their shared session and event contracts.

models: Message blocks, session details and mutation results.
session_store: Backend-neutral transcript keys, records and persistence contract.
local_session_store: Workspace-local JSONL transcripts and session operations.
base: Agent reply streams and session-management contract.
claude: Claude Code backend, message projection, storage adaptation and Job tools.

Only session models load here. Public messages and presentation patches live
in axonx.client.events. Import backends and stores explicitly.
"""

from . import models

__all__ = [
    "models",
]
