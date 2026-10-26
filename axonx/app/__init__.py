"""Application capabilities and their public package and module namespaces.

config: Application configuration discovery, inheritance, validation and resolution.
workspace: Workspace browsing, file previews and staged uploads.
components: Managed service, Agent, Job, sync and scheduling domains.
steps: Job adapters for application capabilities.
core: Application composition, lifecycle, dispatch and response completion.
crontabs: Installed schedule lookup, parsing and command validation.
constants: Shared application defaults and resource limits.
registry: Provider declarations, validation and application-local lookup.

This package is a namespace. Import runtime capabilities from their owning
modules, such as core.application.Application. Public service contracts live
in axonx.client.
"""
