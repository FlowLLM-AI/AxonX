"""Focused regression tests for shared utility boundaries."""

from __future__ import annotations

import os
import sys

import pytest

from axonx.plugin_kit.loading import load_symbol
from axonx.utils.env import find_env_file, load_env
from axonx.utils.fs import directory_sha256
from axonx.utils.logging import (
    LoggingConfig,
    configure_logging,
    get_log_path,
    get_logger,
)


def test_dotenv_does_not_override_process_environment(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("EXISTING=dotenv\nNEW_VALUE=loaded\n", encoding="utf-8")
    monkeypatch.setenv("EXISTING", "process")
    monkeypatch.delenv("NEW_VALUE", raising=False)

    assert find_env_file(tmp_path) == env_file
    assert load_env(env_file) == {"EXISTING": "process", "NEW_VALUE": "loaded"}
    assert os.environ["EXISTING"] == "process"


def test_directory_hash_frames_file_contents_unambiguously(tmp_path):
    one = tmp_path / "one"
    two = tmp_path / "two"
    one.mkdir()
    two.mkdir()
    marker = len(b"b").to_bytes(4, "big") + b"b"
    (one / "a").write_bytes(b"x" + marker)
    (two / "a").write_bytes(b"x")
    (two / "b").write_bytes(b"")

    assert directory_sha256(one) != directory_sha256(two)


def test_directory_hash_refuses_symlinks(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    target = tmp_path / "outside"
    target.write_text("secret", encoding="utf-8")
    try:
        (root / "link").symlink_to(target)
    except OSError:
        pytest.skip("Symlinks are unavailable")

    with pytest.raises(ValueError, match="does not allow symlinks"):
        directory_sha256(root)


def test_symbol_loading_never_reexecutes_an_imported_module(tmp_path, monkeypatch):
    module_name = "axonx_test_plugin_loading"
    module_path = tmp_path / f"{module_name}.py"
    module_path.write_text(
        "loads = globals().get('loads', 0) + 1\nclass Candidate: pass\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop(module_name, None)

    first = load_symbol(f"{module_name}:Candidate", object, kind="Task")
    second = load_symbol(f"{module_name}:Candidate", object, kind="Task")

    assert first is second
    assert sys.modules[module_name].loads == 1


def test_logging_configuration_is_explicit(tmp_path):
    configure_logging(
        LoggingConfig(log_dir=tmp_path, log_to_console=False, log_to_file=True)
    )
    get_logger("probe").info("configured")

    path = get_log_path()
    assert path is not None
    assert path.parent == tmp_path.resolve()
    assert "configured" in path.read_text(encoding="utf-8")

    configure_logging(LoggingConfig(log_to_console=False, log_to_file=False))
