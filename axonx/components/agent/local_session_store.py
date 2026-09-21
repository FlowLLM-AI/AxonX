"""Workspace-local JSONL implementation of the Agent session store."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import time
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import cast
from uuid import uuid4

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
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._seen_uuids: dict[str, set[str]] = {}

    @staticmethod
    def _part(value: str, label: str) -> str:
        if not value or not _KEY_PART.fullmatch(value):
            raise ValueError(f"Invalid Agent session {label}: {value!r}")
        return value

    @classmethod
    def _subpath(cls, value: str) -> PurePosixPath:
        path = PurePosixPath(value)
        if path.is_absolute() or not path.parts or any(
            part in {"", ".", ".."} or not _KEY_PART.fullmatch(part)
            for part in path.parts
        ):
            raise ValueError(f"Invalid Agent session subpath: {value!r}")
        return path

    def _session_dir(self, project_key: str, session_id: str) -> Path:
        return self.root / self._part(project_key, "project_key") / self._part(
            session_id, "session_id"
        )

    def _path(self, key: AgentSessionKey) -> Path:
        directory = self._session_dir(key["project_key"], key["session_id"])
        subpath = key.get("subpath")
        if subpath is None:
            return directory / "transcript.jsonl"
        return directory / self._subpath(subpath).with_suffix(".jsonl")

    def _summary_path(self, key: AgentSessionListKey) -> Path:
        return self._session_dir(key["project_key"], key["session_id"]) / "summary.json"

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

    async def append(
        self, key: AgentSessionKey, entries: list[AgentSessionEntry]
    ) -> None:
        if not entries:
            return
        path = self._path(key)
        async with self._locks[str(path)]:
            cache_key = str(path)
            known = self._seen_uuids.get(cache_key)
            if known is None:
                existing = await asyncio.to_thread(self._read, path) or []
                known = {
                    entry["uuid"]
                    for entry in existing
                    if isinstance(entry.get("uuid"), str)
                }
                self._seen_uuids[cache_key] = known
            appended: list[AgentSessionEntry] = []
            for entry in entries:
                if not isinstance(entry, dict) or not isinstance(entry.get("type"), str):
                    raise ValueError("Session entries require a string type")
                uuid = entry.get("uuid")
                if isinstance(uuid, str) and uuid in known:
                    continue
                if isinstance(uuid, str):
                    known.add(uuid)
                # Round-trip through JSON to reject non-JSON values and detach callers.
                appended.append(cast(AgentSessionEntry, json.loads(json.dumps(entry))))
            if not appended:
                return
            content = "".join(
                json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n"
                for entry in appended
            )

            def append_file() -> None:
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())

            await asyncio.to_thread(append_file)

    async def load(self, key: AgentSessionKey) -> list[AgentSessionEntry] | None:
        path = self._path(key)
        async with self._locks[str(path)]:
            entries = await asyncio.to_thread(self._read, path)
        return json.loads(json.dumps(entries)) if entries is not None else None

    async def list_sessions(self, project_key: str) -> list[AgentSessionListEntry]:
        project = self.root / self._part(project_key, "project_key")

        def scan() -> list[AgentSessionListEntry]:
            try:
                directories = tuple(project.iterdir())
            except FileNotFoundError:
                return []
            result: list[AgentSessionListEntry] = []
            for directory in directories:
                transcript = directory / "transcript.jsonl"
                if not directory.is_dir() or not transcript.is_file():
                    continue
                result.append(
                    {
                        "session_id": directory.name,
                        "mtime": int(transcript.stat().st_mtime * 1000),
                    }
                )
            return sorted(result, key=lambda item: item["mtime"], reverse=True)

        return await asyncio.to_thread(scan)

    async def load_summary(
        self, key: AgentSessionListKey
    ) -> AgentSessionSummary | None:
        path = self._summary_path(key)

        def read() -> AgentSessionSummary | None:
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                return None
            if (
                not isinstance(value, dict)
                or value.get("session_id") != key["session_id"]
                or not isinstance(value.get("mtime"), int)
                or not isinstance(value.get("data"), dict)
            ):
                raise ValueError(f"Invalid Agent session summary: {path}")
            return cast(AgentSessionSummary, value)

        async with self._locks[str(path)]:
            return await asyncio.to_thread(read)

    async def save_summary(
        self, key: AgentSessionListKey, summary: AgentSessionSummary
    ) -> AgentSessionSummary:
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
                "mtime": max(int(time.time() * 1000), transcript_mtime),
                "data": json.loads(json.dumps(summary["data"])),
            }
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
            temporary.write_text(
                json.dumps(stored, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            os.replace(temporary, path)
            return stored

        async with self._locks[str(path)]:
            return await asyncio.to_thread(write)

    async def list_summaries(self, project_key: str) -> list[AgentSessionSummary]:
        project = self.root / self._part(project_key, "project_key")

        def scan() -> list[AgentSessionSummary]:
            try:
                paths = tuple(project.glob("*/summary.json"))
            except FileNotFoundError:
                return []
            summaries: list[AgentSessionSummary] = []
            for path in paths:
                value = json.loads(path.read_text(encoding="utf-8"))
                if (
                    not isinstance(value, dict)
                    or not isinstance(value.get("session_id"), str)
                    or not isinstance(value.get("mtime"), int)
                    or not isinstance(value.get("data"), dict)
                ):
                    raise ValueError(f"Invalid Agent session summary: {path}")
                summaries.append(cast(AgentSessionSummary, value))
            return summaries

        return await asyncio.to_thread(scan)

    async def delete(self, key: AgentSessionKey) -> None:
        path = self._path(key)
        async with self._locks[str(path)]:
            if key.get("subpath") is None:
                await asyncio.to_thread(
                    shutil.rmtree,
                    self._session_dir(key["project_key"], key["session_id"]),
                    True,
                )
                prefix = str(self._session_dir(key["project_key"], key["session_id"]))
                for cached in tuple(self._seen_uuids):
                    if cached.startswith(prefix):
                        self._seen_uuids.pop(cached, None)
            else:
                await asyncio.to_thread(path.unlink, missing_ok=True)
                self._seen_uuids.pop(str(path), None)

    async def list_subkeys(self, key: AgentSessionListKey) -> list[str]:
        base = self._session_dir(key["project_key"], key["session_id"])

        def scan() -> list[str]:
            try:
                paths = tuple(
                    path
                    for path in base.rglob("*.jsonl")
                    if path != base / "transcript.jsonl"
                )
            except FileNotFoundError:
                return []
            return sorted(str(path.relative_to(base).with_suffix("")) for path in paths)

        return await asyncio.to_thread(scan)
