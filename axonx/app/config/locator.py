"""Shared name, path and installed entry-point lookup for configuration files."""

from importlib import import_module
from importlib import metadata
from pathlib import Path


def discover_files(directory: Path, extensions: tuple[str, ...]) -> dict[str, Path]:
    """Prefer extensions in their declared order when names coincide."""
    if not directory.is_dir():
        return {}
    paths = sorted(
        (path for path in directory.iterdir() if path.is_file() and path.suffix in extensions),
        key=lambda path: (extensions.index(path.suffix), path.name),
    )
    return {path.stem: path for path in reversed(paths)}


def locate_file(
    source: str | Path,
    *,
    directory: Path,
    extensions: tuple[str, ...],
    group: str,
    label: str,
) -> Path:
    """Locate a built-in name, installed contribution or explicit file path."""
    name = str(source)
    builtins = discover_files(directory, extensions)
    entries = list(metadata.entry_points().select(group=group, name=name))
    if name in builtins and entries:
        raise ValueError(f"{label} '{name}' is provided by both AxonX and an installed distribution")
    if name in builtins:
        return builtins[name]
    if len(entries) > 1:
        raise ValueError(f"{label} {name!r} has multiple installed providers")
    entry = entries[0] if entries else None
    if entry is not None:
        module = import_module(entry.module)
        if entry.attr and hasattr(module, entry.attr):
            loaded = entry.load()
            path = Path(loaded() if callable(loaded) else loaded)
        else:
            locations = list(getattr(module, "__path__", ()))
            if len(locations) != 1:
                raise ValueError(f"{label} entry point '{name}' must target one package directory")
            folder = Path(locations[0])
            stem = entry.attr or name
            path = next(
                (folder / f"{stem}{ext}" for ext in extensions if (folder / f"{stem}{ext}").is_file()),
                folder / f"{stem}{extensions[0]}",
            )
        if path.suffix not in extensions or not path.is_file():
            raise ValueError(f"{label} entry point '{name}' did not resolve to a supported file: {path}")
        return path
    path = Path(name).expanduser()
    if path.suffix in extensions:
        for candidate in ((path,) if path.is_absolute() else (path, directory / path)):
            if candidate.is_file():
                return candidate
    known = ", ".join(sorted(builtins)) or "none"
    raise FileNotFoundError(f"{label} file not found: {name}. Available: {known}")
