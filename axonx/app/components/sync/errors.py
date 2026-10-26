"""Distinguish changing source snapshots from deterministic replica failures."""


class SnapshotChangedError(OSError):
    """A source changed while its display replica was being prepared."""


class ReplicaBudgetError(ValueError):
    """Required, non-sampleable files cannot fit the transfer budget."""
