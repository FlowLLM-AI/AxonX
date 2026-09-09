"""Application- and invocation-scoped shared state."""

from .schema import ApplicationConfig, Response


class ApplicationContext:
    """Hold shared state for every component in one application instance."""

    def __init__(self, registry, **config):
        self.registry = registry
        self.app_config = ApplicationConfig(**config)
        self.components = {}
        self.jobs = {}
        self.metadata = {}


class RuntimeContext(dict):
    """Share invocation data and the response across one job's steps."""

    def __init__(self, **data):
        super().__init__(data)
        self.response = Response()

    @property
    def data(self):
        """Return this mapping for compatibility with context consumers."""
        return self
