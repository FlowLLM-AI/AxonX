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
from .session_store import (
    AgentSessionEntry,
    AgentSessionKey,
    AgentSessionListEntry,
    AgentSessionListKey,
    AgentSessionSummary,
)

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

    def _path(self, key: AgentSessionKey) -> Path:
        directory = self._session_dir(key["project_key"], key["session_id"])
        subpath = key.get("subpath")
        if subpath is None:
            return self._inside(directory / "transcript.jsonl")
        for part in subpath.split("/"):
            self._part(part, "subpath")
        if subpath == "transcript":
            raise ValueError("Agent session subpath 'transcript' is reserved")
        return self._inside(directory / f"{subpath}.jsonl")

    def _summary_path(self, key: AgentSessionListKey) -> Path:
        return self._inside(self._session_dir(key["project_key"], key["session_id"]) / "summary.json")

    async def _io[T](self, key: AgentSessionListKey, operation: Callable[[], T]) -> T:
        # Keep the session locked until disk work ends, including after caller cancellation.
        async with self._locks[self._session_dir(key["project_key"], key["session_id"])]:
            return await run_blocking(operation)

    @staticmethod
    def _read(path: Path) -> list[AgentSessionEntry] | None:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return None
        entries: list[AgentSessionEntry] = []
        for number, line in enumerate(lines, start=1):
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid session JSONL at {path}:{number}") from exc
            if not isinstance(value, dict) or not isinstance(value.get("type"), str):
                raise ValueError(f"Invalid session entry at {path}:{number}")
            entries.append(cast(AgentSessionEntry, value))
        return entries

    async def append(self, key: AgentSessionKey, entries: list[AgentSessionEntry]) -> None:
        if not entries:
            return
        path = self._path(key)

        def write() -> None:
            known = self._seen_uuids.get(path)
            if known is None:
                existing = self._read(path) or []
                known = {entry["uuid"] for entry in existing if isinstance(entry.get("uuid"), str)}
            pending_uuids = set(known)
            lines: list[str] = []
            for entry in entries:
                if not isinstance(entry, dict) or not isinstance(entry.get("type"), str):
                    raise ValueError("Session entries require a string type")
                uuid = entry.get("uuid")
                if isinstance(uuid, str) and uuid in pending_uuids:
                    continue
                if isinstance(uuid, str):
                    pending_uuids.add(uuid)
                lines.append(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
            if not lines:
                return
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as stream:
                    stream.write("".join(lines))
                    stream.flush()
                    os.fsync(stream.fileno())
            except OSError:
                self._seen_uuids.pop(path, None)
                raise
            self._seen_uuids[path] = pending_uuids

        await self._io(key, write)

    async def load(self, key: AgentSessionKey) -> list[AgentSessionEntry] | None:
        path = self._path(key)
        return await self._io(key, lambda: self._read(path))

    async def list_sessions(self, project_key: str) -> list[AgentSessionListEntry]:
        project = self._inside(self.root / self._part(project_key, "project_key"))

        def scan() -> list[AgentSessionListEntry]:
            try:
                directories = tuple(project.iterdir())
            except FileNotFoundError:
                return []
            result: list[AgentSessionListEntry] = []
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

    async def load_summary(self, key: AgentSessionListKey) -> AgentSessionSummary | None:
        path = self._summary_path(key)

        return await self._io(key, lambda: self._read_summary(path))

    @staticmethod
    def _read_summary(path: Path) -> AgentSessionSummary | None:
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
        return cast(AgentSessionSummary, value)

    async def save_summary(self, key: AgentSessionListKey, summary: AgentSessionSummary) -> AgentSessionSummary:
        path = self._summary_path(key)
        transcript = self._path(key)
        if summary["session_id"] != key["session_id"]:
            raise ValueError("Agent session summary ID does not match its key")

        def write() -> AgentSessionSummary:
            try:
                transcript_mtime = int(transcript.stat().st_mtime * 1000)
            except FileNotFoundError as exc:
                raise ValueError("Cannot save a summary without a transcript") from exc
            stored: AgentSessionSummary = {
                "session_id": summary["session_id"],
                "mtime": transcript_mtime,
                "data": summary["data"],
            }
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
            content = json.dumps(stored, ensure_ascii=False, separators=(",", ":"))
            try:
                temporary.write_text(content, encoding="utf-8")
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
            return json.loads(content)

        return await self._io(key, write)

    async def list_summaries(self, project_key: str) -> list[AgentSessionSummary]:
        project = self._inside(self.root / self._part(project_key, "project_key"))

        def scan() -> list[AgentSessionSummary]:
            summaries: list[AgentSessionSummary] = []
            for path in project.glob("*/summary.json"):
                value = self._read_summary(self._inside(path))
                if value is not None:
                    summaries.append(value)
            return summaries

        return await asyncio.to_thread(scan)

    async def delete(self, key: AgentSessionKey) -> None:
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

    async def list_subkeys(self, key: AgentSessionListKey) -> list[str]:
        base = self._session_dir(key["project_key"], key["session_id"])

        def scan() -> list[str]:
            paths = (self._inside(path) for path in base.rglob("*.jsonl") if path != base / "transcript.jsonl")
            return sorted(str(path.relative_to(base).with_suffix("")) for path in paths)

        return await self._io(key, scan)
