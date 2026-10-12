"""Atomic file snapshots for immutable task inputs."""

import os
import shutil
from pathlib import Path

from .atomic import atomic_write


def snapshot_file(source: Path, target: Path) -> None:
    """Keep an atomically replaced source stable without duplicating its contents."""

    source = Path(source).resolve(strict=True)

    def copy(temporary):
        temporary.unlink()
        try:
            os.link(source, temporary)
        except OSError:
            shutil.copyfile(source, temporary)

    atomic_write(target, copy)
