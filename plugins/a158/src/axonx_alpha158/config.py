"""Expose the Alpha158 demo application configuration."""

from pathlib import Path


def config_path() -> Path:
    """Return the packaged Alpha158 configuration file."""
    return Path(__file__).with_name("config.yaml")
