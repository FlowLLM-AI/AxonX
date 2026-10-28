"""Research Task plugin capabilities and their public module namespaces.

models: Plugin metadata and validated wheel artifacts.
manifest: Task-only YAML manifests, package entries and registration validation.
fingerprint: Source-cache, wheel-archive and installed-content SHA-256 fingerprints.
discovery: Installed plugin lookup, provenance and broken-installation diagnostics.
wheel: Cached wheel builds and archive inspection without importing plugin code.
installer: Artifact preparation, dependency installation, editable installs and removal.
"""

from . import discovery, fingerprint, installer, manifest, models, wheel

__all__ = [
    "discovery",
    "fingerprint",
    "installer",
    "manifest",
    "models",
    "wheel",
]
