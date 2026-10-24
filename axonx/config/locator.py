"""Shared name, path and installed entry-point lookup for configuration files."""

from importlib import import_module
from pathlib import Path

from .entry_points import find_entry_points, load_entry_point, unique_entry_point


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
    entries = find_entry_points(group, name)
    if name in builtins and entries:
        raise ValueError(f"{label} '{name}' is provided by both AxonX and an installed distribution")
    if name in builtins:
        return builtins[name]
    entry = unique_entry_point(entries, name, label)
    if entry is not None:
        module = import_module(entry.module)
        if entry.attr and hasattr(module, entry.attr):
            path = Path(load_entry_point(entry, invoke=True))
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
