"""Enumeration contract tests."""

from axonx.enumeration import TaskType


def test_task_type_values() -> None:
    """Task type values remain stable for serialized status records."""
    assert [task_type.value for task_type in TaskType] == [
        "ingestion",
        "etl",
        "analysis",
        "training",
        "inference",
        "backtest",
    ]
