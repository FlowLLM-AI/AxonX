"""Verify application-owned display replica application."""

import pytest

from axonx.app.components.sync.applier import TaskArchiveApplier


@pytest.mark.parametrize("budget", [0, -1, True, None])
def test_task_archive_budget_is_validated_before_mutation(tmp_path, budget):
    with pytest.raises(ValueError, match="positive integer"):
        TaskArchiveApplier(tmp_path, budget)
