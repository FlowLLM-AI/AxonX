"""Application-scoped configuration, registry, and component collections."""

from ..schema import ApplicationConfig


class ApplicationContext:
    """Hold shared state for every component in one application instance."""

    def __init__(self, registry, **config):
        self.registry = registry
        self.app_config = ApplicationConfig(**config)
        self.components = {}
        self.jobs = {}
        self.metadata = {}
