"""Local Claude transcripts with incremental summaries in the same session lock."""

from __future__ import annotations

from ..models import SessionEntry, SessionKey
from ..session_store import LocalAgentSessionStore


class ClaudeSessionStore(LocalAgentSessionStore):
    """Implement the SDK store directly, including cancellation-safe summary updates."""

    async def append(self, key: SessionKey, entries: list[SessionEntry]) -> None:
        from claude_agent_sdk import fold_session_summary

        if not entries:
            return

        def write() -> None:
            path = self._path(key)
            if key.get("subpath") is not None:
                self._append(path, entries)
                return
            summary_path = self._summary_path(key)
            previous = self._read_summary(summary_path)
            if previous is not None and (not path.is_file() or previous["mtime"] != int(path.stat().st_mtime * 1000)):
                previous = None
            pending = self._append(path, entries)
            if previous is not None and not pending:
                return
            try:
                if previous is None:
                    pending = self._read(path) or []
                self._save_summary(key, fold_session_summary(previous, key, pending))
            except Exception:
                # The transcript is durable; force a rebuild if summary publication fails.
                summary_path.unlink(missing_ok=True)
                raise

        await self._io(key, write)
