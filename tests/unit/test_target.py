"""One service address format for CLI clients and configured targets."""

import pytest

from axonx.config import ApplicationConfig
from axonx.utils.target import normalize_target


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("127.0.0.1:1024", "http://127.0.0.1:1024"),
        ("https://example.test:443", "https://example.test:443"),
        ("[::1]:1024", "http://[::1]:1024"),
        ("[0:0:0:0:0:0:0:1]:1024", "http://[::1]:1024"),
    ],
)
def test_normalize_target(value, expected):
    assert normalize_target(value) == expected


@pytest.mark.parametrize("value", ["127.0.0.1", "127.0.0.1:0", "http://x:1024/path"])
def test_target_requires_service_address(value):
    with pytest.raises(ValueError):
        normalize_target(value)


def test_configured_targets_are_resolved_by_address():
    config = ApplicationConfig(targets=[{"address": "192.0.2.10:1024"}])
    assert config.resolve_target("http://192.0.2.10:1024") == config.targets[0]
