"""Application update admission and status.

manager: Update-backend contract, maintenance admission and response-completion handoff.
"""

from . import manager
from .manager import UpdateManager

__all__ = [
    "UpdateManager",
    "manager",
]
