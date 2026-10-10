"""The Alpha158 ETL target is the framework fixed-day raw return."""

from axonx_qlib_a158.internal.etl_pipeline import (
    LABELS,
    LABEL_OUTPUTS,
    MARKET_STATE_COLUMNS,
)


def test_etl_has_no_training_transforms_or_future_execution_columns():
    assert LABELS == ("label_return",)
    assert LABEL_OUTPUTS == ("label_return", "label_valid")
    assert not set(MARKET_STATE_COLUMNS) & {
        "exit_date",
        "exit_delayed",
        "entry_date",
        "exit_is_sellable",
    }
