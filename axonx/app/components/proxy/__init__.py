"""Proxy contracts and built-in forwarding implementations.

base: Proxy contract, streaming response ownership, and forwarding errors.
http: HTTP forwarding, upstream connection lifecycle, and URL/header handling.
"""

from . import base, http

__all__ = [
    "base",
    "http",
]
