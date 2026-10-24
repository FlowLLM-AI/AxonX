"""Service component contracts and built-in implementations."""

from .base import BaseService
from .http import HttpService

__all__ = ["BaseService", "HttpService"]
