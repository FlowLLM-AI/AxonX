"""Mutable per-job runtime context and response container."""

from ..schema import Response


class RuntimeContext(dict):
    """Share invocation data and the response across one job's steps."""

    def __init__(self, **data):
        super().__init__(data)
        self.response = Response()

    @property
    def data(self):
        """Return this mapping for compatibility with context consumers."""
        return self
