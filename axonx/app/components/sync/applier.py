"""Receive bounded file batches without interpreting Task or artifact metadata."""

from __future__ import annotations

import os
import shutil
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

from ....task.storage.files import copy_file, file_lock
from ....task.storage.workspace import resolve_relative_path
from .models import MANIFEST_NAME, TAR_PADDING_BYTES, FileGroup, FileManifest, SyncFilesReport, archived_bytes

MAX_ARCHIVE_MEMBERS = 100_000


def _relative(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if not path.parts or path.is_absolute() or ".." in path.parts or path.as_posix() != name or "\\" in name:
        raise ValueError(f"Invalid sync path: {name}")
    return path


def _directories(groups: dict[str, FileGroup]) -> dict[str, FileGroup]:
    """The newest publication owns the current bytes of shared directories."""
    result = {}
    for group in sorted(groups.values(), key=lambda item: item.revision):
        result.update({path: group for path in group.directories})
    return result


class _Receipt(FileManifest):
    """Local directory identities keep an old receipt from adopting a replacement."""

    installed: dict[str, str]


def _directory_identity(path: Path) -> str:
    stat = path.stat()
    return f"{stat.st_dev}:{stat.st_ino}"


class FileSyncStore:
    """Own file receipts, delta reconstruction and rollback under one publication lease."""

    def __init__(self, workspace_path: Path, transfer_budget_bytes: int) -> None:
        if (
            isinstance(transfer_budget_bytes, bool)
            or not isinstance(transfer_budget_bytes, int)
            or transfer_budget_bytes <= 0
        ):
            raise ValueError("transfer_budget_bytes must be a positive integer")
        self.root = Path(workspace_path).expanduser().resolve()
        self.budget = transfer_budget_bytes
        self.state = resolve_relative_path(self.root, "sync/receipts")

    def _receipts(self) -> dict[str, _Receipt]:
        result = {}
        for path in self.state.glob("*.json"):
            manifest = _Receipt.model_validate_json(path.read_bytes())
            if path.stem != manifest.source:
                raise ValueError("Sync receipt source differs from its filename")
            result[manifest.source] = manifest
        return result

    def _path(self, relative: str) -> Path:
        _relative(relative)
        return resolve_relative_path(self.root, relative)

    def index(self, source: str) -> dict[str, dict]:
        """Return complete receipts whose installed file inventories still match."""
        FileManifest(source=source, groups={})
        with file_lock(self.state / "publication.lock"):
            receipt = self._receipts().get(source)
            if receipt is None:
                return {}
            current = _directories(receipt.groups)
            valid = set()
            for relative, group in current.items():
                try:
                    directory = self._path(relative)
                    if _directory_identity(directory) != receipt.installed.get(relative):
                        continue
                    self._verify(directory, group.directories[relative])
                except (OSError, ValueError):
                    continue
                valid.add(relative)
            return {
                name: group.model_copy(
                    update={
                        "directories": {
                            relative: current[relative].directories[relative] for relative in group.directories
                        }
                    }
                ).model_dump(mode="json")
                for name, group in receipt.groups.items()
                if group.directories.keys() <= valid
            }

    @staticmethod
    def _verify(directory: Path, files: dict) -> None:
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError(f"Missing sync directory: {directory}")
        actual = set()
        for path in directory.rglob("*"):
            if path.is_symlink():
                raise ValueError(f"Sync files cannot be symlinks: {path}")
            if path.is_file():
                actual.add(path.relative_to(directory).as_posix())
        if actual != set(files):
            raise ValueError(f"Sync file inventory differs: {directory}")
        for name, record in files.items():
            if (directory / name).stat().st_size != record.size:
                raise ValueError(f"Sync file size differs: {directory}/{name}")

    def apply(self, archive_path: Path, archive_name: str | None = None) -> SyncFilesReport:
        if archive_path.stat().st_size > self.budget:
            raise ValueError(f"Sync archive exceeds {self.budget} bytes")
        with file_lock(self.state / "publication.lock"):
            receipts = self._receipts()
            temporary_root = resolve_relative_path(self.root, "tmp/sync")
            temporary_root.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="receive-", dir=temporary_root) as temporary:
                staging = Path(temporary)
                manifest, count = self._extract(archive_path, staging / "incoming")
                previous = receipts.get(manifest.source, _Receipt(source=manifest.source, groups={}, installed={}))
                for name, group in manifest.groups.items():
                    old = previous.groups.get(name)
                    if old is not None and (
                        group.revision < old.revision or (group.revision == old.revision and group != old)
                    ):
                        raise ValueError(f"Stale or conflicting file batch: {name}")
                incoming = _directories(manifest.groups)
                current = _directories(previous.groups)
                for relative, group in incoming.items():
                    old = current.get(relative)
                    if old is not None and (
                        group.revision < old.revision
                        or (group.revision == old.revision and group.directories[relative] != old.directories[relative])
                    ):
                        raise ValueError(f"Stale or conflicting shared directory: {relative}")
                merged = _Receipt(
                    source=manifest.source,
                    groups={**previous.groups, **manifest.groups},
                    installed={},
                )
                retained = _directories(merged.groups)
                others = {
                    path
                    for source, receipt in receipts.items()
                    if source != manifest.source
                    for group in receipt.groups.values()
                    for path in group.directories
                }
                obsolete = set(current) - set(retained)
                # A receipt owns the installed directory, not a later local replacement at the same path.
                for relative in set(incoming) | obsolete:
                    target = self._path(relative)
                    if relative in others or (
                        target.exists() and _directory_identity(target) != previous.installed.get(relative)
                    ):
                        raise ValueError(f"Cannot overwrite an unowned sync directory: {relative}")
                self._hydrate(staging / "incoming", incoming, current)
                merged.installed = {
                    relative: (
                        _directory_identity(staging / "incoming" / relative)
                        if relative in incoming
                        else previous.installed[relative]
                    )
                    for relative in retained
                }
                receipt_path = staging / "receipt.json"
                receipt_path.write_text(merged.model_dump_json(), encoding="utf-8")
                self._commit(staging, set(incoming), obsolete, manifest.source, receipt_path)
        return SyncFilesReport(archive_name, sorted(incoming), sorted(obsolete), count)

    def _extract(self, archive_path: Path, target: Path) -> tuple[FileManifest, int]:
        try:
            with tarfile.open(archive_path, "r:gz") as archive:
                members, names, expanded = [], set(), TAR_PADDING_BYTES
                for member in archive:
                    if len(members) >= MAX_ARCHIVE_MEMBERS:
                        raise ValueError(f"Sync archive exceeds {MAX_ARCHIVE_MEMBERS} members")
                    expanded += archived_bytes(member.size)
                    if member.size < 0 or expanded > self.budget:
                        raise ValueError("Sync archive expands beyond the configured limit")
                    members.append(member)
                    _relative(member.name)
                    if member.name in names or not member.isfile():
                        raise ValueError(f"Duplicate or nonregular sync member: {member.name}")
                    names.add(member.name)
                if MANIFEST_NAME not in names:
                    raise ValueError("Sync archive is missing its file manifest")
                with archive.extractfile(MANIFEST_NAME) as stream:
                    manifest = FileManifest.model_validate_json(stream.read())
                expected = self._manifest_files(manifest)
                for member in members:
                    if member.name != MANIFEST_NAME and (
                        member.name not in expected or member.size != expected[member.name].size
                    ):
                        raise ValueError(f"Unexpected sync payload: {member.name}")
                target.mkdir()
                archive.extractall(
                    target, members=[item for item in members if item.name != MANIFEST_NAME], filter="data"
                )
                return manifest, len(members) - 1
        except tarfile.TarError as exc:
            raise ValueError(f"Invalid sync archive: {exc}") from exc

    def _manifest_files(self, manifest: FileManifest) -> dict:
        directories = set()
        expected = {}
        for group in manifest.groups.values():
            for relative, files in group.directories.items():
                path = _relative(relative)
                if (
                    not (
                        (path.parts[:1] == ("tasks",) and len(path.parts) == 3)
                        or (path.parts[:2] == ("tmp", "tasks") and len(path.parts) == 4)
                    )
                    or not files
                ):
                    raise ValueError(
                        f"Sync destination must be a nonempty directory under tasks/ or tmp/tasks/: {relative}"
                    )
                if relative in directories:
                    raise ValueError(f"Overlapping sync groups in one batch: {relative}")
                self._path(relative)
                directories.add(relative)
                for name, record in files.items():
                    _relative(name)
                    expected[f"{relative}/{name}"] = record
        if (
            TAR_PADDING_BYTES
            + archived_bytes(len(manifest.model_dump_json().encode()))
            + sum(archived_bytes(record.size) for record in expected.values())
            > self.budget
        ):
            raise ValueError("Reconstructed sync batch exceeds the transfer budget")
        return expected

    def _hydrate(self, extracted: Path, incoming: dict, current: dict) -> None:
        for relative, group in incoming.items():
            files = group.directories[relative]
            old_files = current[relative].directories[relative] if relative in current else {}
            directory = extracted / relative
            directory.mkdir(parents=True, exist_ok=True)
            for name, record in files.items():
                target = directory / name
                if target.is_file():
                    continue
                source = self._path(f"{relative}/{name}")
                if old_files.get(name) != record or source.stat().st_size != record.size:
                    raise ValueError(f"Missing or changed sync delta base: {relative}/{name}")
                target.parent.mkdir(parents=True, exist_ok=True)
                copy_file(source, target)
            self._verify(directory, files)

    def _commit(self, staging: Path, incoming: set[str], obsolete: set[str], source: str, receipt: Path) -> None:
        replacements = [(staging / "incoming" / name, self._path(name)) for name in sorted(incoming)]
        replacements.append((receipt, self.state / f"{source}.json"))
        targets = [target for _, target in replacements] + [self._path(name) for name in sorted(obsolete)]
        backups, installed = [], []
        try:
            for index, target in enumerate(targets):
                if target.is_symlink():
                    raise ValueError(f"Sync destination cannot be a symlink: {target}")
                if target.exists():
                    backup = staging / "backup" / str(index)
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(target, backup)
                    backups.append((target, backup))
            for incoming_path, target in replacements:
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(incoming_path, target)
                installed.append(target)
        except BaseException:
            for target in reversed(installed):
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            for target, backup in reversed(backups):
                os.replace(backup, target)
            raise
