"""Load ``.env`` files into ``os.environ``."""

from __future__ import annotations

import os
from pathlib import Path
from threading import RLock


class EnvLoader:
    """Load env files with an isolated discovery cache."""

    def __init__(self, *, search_depth: int = 5) -> None:
        if search_depth < 0:
            raise ValueError("search_depth must not be negative")
        self.search_depth = search_depth
        self._lock = RLock()
        self._loaded = False
        self._loaded_values: dict[str, str] = {}

    @staticmethod
    def parse(path: str | Path) -> dict[str, str]:
        """Parse a simple ``KEY=VALUE`` file without changing the environment."""
        values: dict[str, str] = {}
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key := key.strip():
                values[key] = value.strip().strip("'\"")
        return values

    @staticmethod
    def _apply(values: dict[str, str], *, override: bool) -> dict[str, str]:
        loaded = {key: value for key, value in values.items() if override or key not in os.environ}
        os.environ.update(loaded)
        return loaded

    def load(
        self,
        path: str | Path | None = None,
        *,
        override: bool = True,
    ) -> dict[str, str]:
        """Load an explicit file or the nearest discovered ``.env`` file."""
        with self._lock:
            if path is None and self._loaded:
                return dict(self._loaded_values)

            if path is not None:
                env_path = Path(path)
                if not env_path.is_file():
                    return {}
                return self._apply(self.parse(env_path), override=override)

            cwd = Path.cwd()
            directories = (cwd, *cwd.parents[: self.search_depth])
            for directory in directories:
                env_path = directory / ".env"
                if env_path.is_file():
                    self._loaded_values = self._apply(
                        self.parse(env_path),
                        override=override,
                    )
                    self._loaded = True
                    return dict(self._loaded_values)
            return {}


_ENV_LOADER = EnvLoader()


def parse_env_file(path: str | Path) -> dict[str, str]:
    """Parse a simple ``KEY=VALUE`` file without changing the environment."""
    return EnvLoader.parse(path)


def load_env(path: str | Path | None = None, *, override: bool = True) -> dict[str, str]:
    """Load an explicit env file, or discover one from the working directory."""
    return _ENV_LOADER.load(path, override=override)
