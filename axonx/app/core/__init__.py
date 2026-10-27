"""Application assembly and lifecycle.

application: Public application facade and composition-root lifecycle.
banner: Startup banner with AxonX runtime metadata.
composition: Assemble providers, inject dependencies, and order the application lifecycle.
context: Application-scoped runtime state.
dispatch: Validate, log, and route Job invocations.
"""

from . import application, banner, composition, context, dispatch

__all__ = [
    "application",
    "banner",
    "composition",
    "context",
    "dispatch",
]
