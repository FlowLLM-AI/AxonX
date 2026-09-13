"""Generic proxy component contracts and implementations."""

from ...schema import ProxyResponse
from .base import BaseProxyComponent
from .http import HttpProxyComponent

__all__ = ["BaseProxyComponent", "HttpProxyComponent", "ProxyResponse"]
