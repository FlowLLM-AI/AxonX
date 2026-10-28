"""Remotely callable service contracts and implementations.

base: Component contract for remotely callable services.
http: HTTP service implementation and endpoint capabilities.
"""

from . import base, http

__all__ = [
    "base",
    "http",
]
