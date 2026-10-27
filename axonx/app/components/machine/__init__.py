"""Managed machine observation, diagnostics and Python execution.

base: Machine component contract and managed lifecycle.
build_info: Identity of the AxonX build this process is running.
gpu: Discover GPUs and parse metrics reported by vendor command-line tools.
local: Local machine component, runtime diagnostics and target health checks.
models: Immutable resource, diagnostics, target health and execution payloads.
python: Bounded Python subprocess execution and cancellation-safe process cleanup.
"""

from . import base, build_info, gpu, local, models, python

__all__ = [
    "base",
    "build_info",
    "gpu",
    "local",
    "models",
    "python",
]
