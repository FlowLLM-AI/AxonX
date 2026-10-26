"""Application composition, lifecycle and dispatch.

build_info: Installed version, source revision and runtime build identity.
response: Callbacks committed after an enclosing response finishes sending.
graph: Component dependency ordering and cycle detection.
dispatch: Job validation, logging, local routing and remote forwarding.
context: Application-owned components, Jobs, workspace and read-only runtime views.
composition: Provider registration, configuration and isolated runtime assembly.
application: Application startup, rollback, shutdown and public Job invocation.
banner: Startup logo and service metadata rendering.

Only shared value and response-completion contracts load here. Import
Application and its composition machinery from their owning modules.
"""

from . import build_info, response

__all__ = [
    "build_info",
    "response",
]
