from axonx.enumeration import TaskType


def test_task_type_values() -> None:
    assert [task_type.value for task_type in TaskType] == [
        "ingestion",
        "etl",
        "analysis",
        "training",
        "inference",
        "backtest",
    ]
