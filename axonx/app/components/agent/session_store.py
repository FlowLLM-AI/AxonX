"""Workspace-local JSONL implementation of the Agent session store."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import cast
from uuid import uuid4

from ....utils.async_work import run_blocking
from .models import SessionEntry, SessionKey, SessionRecord, SessionSummary

_KEY_PART = re.compile(r"^[A-Za-z0-9._-]+$")


class LocalAgentSessionStore:
    """Persist opaque backend transcripts below one explicitly scoped root."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=False)
        self._locks: defaultdict[Path, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._seen_uuids: dict[Path, set[str]] = {}

    @staticmethod
    def _part(value: str, label: str) -> str:
        if value in {".", ".."} or not _KEY_PART.fullmatch(value):
            raise ValueError(f"Invalid Agent session {label}: {value!r}")
        return value

    def _inside(self, path: Path) -> Path:
        if not path.resolve().is_relative_to(self.root):
            raise ValueError(f"Agent session path leaves the store: {path}")
        return path

    def _session_dir(self, project_key: str, session_id: str) -> Path:
        return self._inside(self.root / self._part(project_key, "project_key") / self._part(session_id, "session_id"))

    def _path(self, key: SessionKey) -> Path:
        directory = self._session_dir(key["project_key"], key["session_id"])
        subpath = key.get("subpath")
        if subpath is None:
            return self._inside(directory / "transcript.jsonl")
        for part in subpath.split("/"):
            self._part(part, "subpath")
        if subpath == "transcript":
            raise ValueError("Agent session subpath 'transcript' is reserved")
        return self._inside(directory / f"{subpath}.jsonl")

    def _summary_path(self, key: SessionKey) -> Path:
        return self._inside(self._session_dir(key["project_key"], key["session_id"]) / "summary.json")

    async def _io[T](self, key: SessionKey, operation: Callable[[], T]) -> T:
        # Keep the session locked until disk work ends, including after caller cancellation.
        async with self._locks[self._session_dir(key["project_key"], key["session_id"])]:
            return await run_blocking(operation)

    @staticmethod
    def _read(path: Path) -> list[SessionEntry] | None:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return None
        entries: list[SessionEntry] = []
        for number, line in enumerate(lines, start=1):
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid session JSONL at {path}:{number}") from exc
            if not isinstance(value, dict) or not isinstance(value.get("type"), str):
                raise ValueError(f"Invalid session entry at {path}:{number}")
            entries.append(cast(SessionEntry, value))
        return entries

    def _append(self, path: Path, entries: list[SessionEntry]) -> list[SessionEntry]:
        """Append once under the session lock; return only newly stored entries."""
        known = self._seen_uuids.get(path)
        if known is None:
            known = {entry["uuid"] for entry in self._read(path) or [] if isinstance(entry.get("uuid"), str)}
        pending_uuids = set(known)
        pending: list[SessionEntry] = []
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("type"), str):
                raise ValueError("Session entries require a string type")
            uuid = entry.get("uuid")
            if isinstance(uuid, str):
                if uuid in pending_uuids:
                    continue
                pending_uuids.add(uuid)
            pending.append(entry)
        if pending:
            content = "".join(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n" for entry in pending)
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
            except OSError:
                self._seen_uuids.pop(path, None)
                raise
            self._seen_uuids[path] = pending_uuids
        return pending

    async def append(self, key: SessionKey, entries: list[SessionEntry]) -> None:
        if entries:
            await self._io(key, lambda: self._append(self._path(key), entries))

    async def load(self, key: SessionKey) -> list[SessionEntry] | None:
        path = self._path(key)
        return await self._io(key, lambda: self._read(path))

    async def exists(self, key: SessionKey) -> bool:
        """Check identity without loading a potentially large transcript."""
        path = self._path(key)
        return await self._io(key, path.is_file)

    async def list_sessions(self, project_key: str) -> list[SessionRecord]:
        project = self._inside(self.root / self._part(project_key, "project_key"))

        def scan() -> list[SessionRecord]:
            try:
                directories = tuple(project.iterdir())
            except FileNotFoundError:
                return []
            result: list[SessionRecord] = []
            for directory in directories:
                transcript = self._inside(directory / "transcript.jsonl")
                if not directory.is_dir() or not transcript.is_file():
                    continue
                try:
                    mtime = int(transcript.stat().st_mtime * 1000)
                except FileNotFoundError:
                    continue
                result.append(
                    {
                        "session_id": directory.name,
                        "mtime": mtime,
                    }
                )
            return sorted(result, key=lambda item: item["mtime"], reverse=True)

        return await asyncio.to_thread(scan)

    @staticmethod
    def _read_summary(path: Path) -> SessionSummary | None:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        if (
            not isinstance(value, dict)
            or value.get("session_id") != path.parent.name
            or not isinstance(value.get("mtime"), int)
            or not isinstance(value.get("data"), dict)
        ):
            raise ValueError(f"Invalid Agent session summary: {path}")
        return cast(SessionSummary, value)

    def _save_summary(self, key: SessionKey, summary: SessionSummary) -> None:
        """Publish a summary under the same lock as its transcript."""
        if summary["session_id"] != key["session_id"]:
            raise ValueError("Agent session summary ID does not match its key")
        path = self._summary_path(key)
        summary = {**summary, "mtime": int(self._path(key).stat().st_mtime * 1000)}
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_text(json.dumps(summary, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    async def list_session_summaries(self, project_key: str) -> list[SessionSummary]:
        project = self._inside(self.root / self._part(project_key, "project_key"))

        def scan() -> list[SessionSummary]:
            summaries: list[SessionSummary] = []
            for path in project.glob("*/summary.json"):
                value = self._read_summary(self._inside(path))
                if value is not None:
                    summaries.append(value)
            return summaries

        return await asyncio.to_thread(scan)

    async def delete(self, key: SessionKey) -> None:
        path = self._path(key)

        def remove() -> None:
            if key.get("subpath") is None:
                directory = path.parent
                if directory.exists():
                    shutil.rmtree(directory)
                for cached in tuple(self._seen_uuids):
                    if cached.is_relative_to(directory):
                        self._seen_uuids.pop(cached, None)
            else:
                path.unlink(missing_ok=True)
                self._seen_uuids.pop(path, None)

        await self._io(key, remove)

    async def list_subkeys(self, key: SessionKey) -> list[str]:
        base = self._session_dir(key["project_key"], key["session_id"])

        def scan() -> list[str]:
            paths = (self._inside(path) for path in base.rglob("*.jsonl") if path != base / "transcript.jsonl")
            return sorted(str(path.relative_to(base).with_suffix("")) for path in paths)

        return await self._io(key, scan)
