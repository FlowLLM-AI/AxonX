"""Remotely callable service contracts and implementations.

base: Managed service lifecycle and application-serving contract.
http: HTTP, SSE, MCP, proxy routes, uploads and optional Studio assets.
"""

from . import base, http
from .base import BaseService
from .http.service import HttpService

__all__ = [
    "BaseService",
    "HttpService",
    "base",
    "http",
]
