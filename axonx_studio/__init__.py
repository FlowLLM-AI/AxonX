"""Static assets for AxonX Studio."""

from pathlib import Path


def static_dir() -> Path:
    """Return the Studio static asset directory."""
    return Path(__file__).resolve().parent / "dist"


__all__ = ["static_dir"]
