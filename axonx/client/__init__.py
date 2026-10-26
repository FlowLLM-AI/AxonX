"""Clients for AxonX services, owned by their callers rather than the App.

base: Transport-independent lifecycle, Job interface and remote errors.
config: Validated connection options, canonical addresses and wire conventions.
models: Public Job responses, catalogs and staged-file results.
events: Public Job streams, Agent messages and shared Task event types.
http: HTTP Jobs, event streams, uploads and short-lived invocation helpers.
mcp: MCP access to the ordinary Job response surface.

This package is a namespace. Import contracts and transport implementations
from their owning modules; reading a contract never loads a transport.
"""
