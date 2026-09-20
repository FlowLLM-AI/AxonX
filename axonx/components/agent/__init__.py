"""Agent component contract and built-in backends."""

from .base import BaseAgentComponent
from .claude import ClaudeAgentComponent

__all__ = ["BaseAgentComponent", "ClaudeAgentComponent"]
