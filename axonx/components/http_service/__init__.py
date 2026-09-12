"""Service component contracts and built-in implementations."""

from .base_service import BaseService
from .http_service import HttpService

__all__ = ["BaseService", "HttpService"]
