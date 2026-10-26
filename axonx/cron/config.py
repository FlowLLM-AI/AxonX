"""Select bundled, installed or explicit crontab files."""

from importlib import import_module, metadata
from pathlib import Path


def resolve_cron(source: str) -> Path:
    """Select a bundled, installed or explicit crontab without coupling Cron to CLI."""
    directory = Path(__file__).resolve().parent
    bundled = {path.stem: path for path in directory.glob("*.cron")}
    entries = list(metadata.entry_points().select(group="axonx.crons", name=source))
    if len(entries) > 1 or (source in bundled and entries):
        raise ValueError(f"Cron {source!r} has multiple providers")
    if source in bundled:
        return bundled[source]
    if entries:
        entry = entries[0]
        module = import_module(entry.module)
        if entry.attr and hasattr(module, entry.attr):
            loaded = entry.load()
            path = Path(loaded() if callable(loaded) else loaded)
        else:
            locations = list(getattr(module, "__path__", ()))
            if len(locations) != 1:
                raise ValueError("A Cron provider must identify one package directory")
            path = Path(locations[0]) / f"{entry.attr or source}.cron"
    else:
        path = Path(source).expanduser()
    if path.suffix != ".cron" or not path.is_file():
        raise FileNotFoundError(f"Cron file not found: {source}")
    return path.resolve()
