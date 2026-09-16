"""Build and fingerprint plugin source trees."""

from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from ..utils.fs import directory_sha256

_IGNORED_PARTS = {".git", ".venv", "__pycache__", "build", "dist", "*.egg-info"}


def source_sha256(path: Path) -> str:
    """Hash stable source paths and contents, excluding generated files."""
    root = path.expanduser().resolve()
    if not (root / "pyproject.toml").is_file():
        raise FileNotFoundError(f"Plugin pyproject.toml not found: {root}")
    return directory_sha256(root, ignored_parts=_IGNORED_PARTS)


def build_wheel(source: Path, output: Path, *, use_cache: bool = False) -> Path:
    """Build exactly one wheel from a Python project using this interpreter."""
    output.mkdir(parents=True, exist_ok=True)
    existing = list(output.glob("*.whl"))
    if use_cache and len(existing) == 1:
        return existing[0]
    with TemporaryDirectory(prefix=".build-", dir=output) as temporary:
        build_output = Path(temporary)
        command = [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--wheel-dir",
            str(build_output),
            str(source),
        ]
        result = subprocess.run(command, check=False, capture_output=True, text=True)
        wheels = list(build_output.glob("*.whl"))
        if result.returncode or len(wheels) != 1:
            detail = (result.stderr or result.stdout).strip()
            raise RuntimeError(f"Plugin wheel build failed: {detail}")
        return wheels[0].replace(output / wheels[0].name)
