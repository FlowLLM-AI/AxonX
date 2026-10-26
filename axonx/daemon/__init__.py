"""Application startup, daemon control, supervision and self-updates.

client: Authenticated daemon requests, update planning and durable status queries.
launcher: Startup validation, supervisor snapshots and application service assembly.
supervisor: Standalone process ownership, restart coordination and control socket.
update: Standalone package/source updates and atomic daemon records.
"""

from . import client, launcher, supervisor, update

__all__ = [
    "client",
    "launcher",
    "supervisor",
    "update",
]
