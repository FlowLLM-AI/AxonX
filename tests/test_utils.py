"""Environment and logging utility tests."""

# Tests favor descriptive function names over repeated docstrings.
# pylint: disable=missing-function-docstring

from axonx.utils import EnvLoader, get_log_path, get_logger


def test_env_loader_discovers_and_caches_nearest_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("AXONX_TEST_VALUE=first\n", encoding="utf-8")
    child = tmp_path / "child"
    child.mkdir()
    monkeypatch.chdir(child)
    monkeypatch.delenv("AXONX_TEST_VALUE", raising=False)

    loader = EnvLoader(search_depth=1)
    assert loader.load() == {"AXONX_TEST_VALUE": "first"}

    env_file.write_text("AXONX_TEST_VALUE=second\n", encoding="utf-8")
    assert loader.load() == {"AXONX_TEST_VALUE": "first"}


def test_get_logger_configures_named_file_sink(tmp_path):
    logger = get_logger(
        "Probe",
        log_dir=tmp_path,
        log_to_console=False,
        force_init=True,
    )
    logger.info(f"value={3}")

    [log_file] = tmp_path.glob("*.log")
    content = log_file.read_text(encoding="utf-8")
    assert "axonx.Probe" in content
    assert "value=3" in content
    assert get_log_path() == log_file.resolve()

    get_logger(log_to_console=False, log_to_file=False, force_init=True)
    assert get_log_path() is None
