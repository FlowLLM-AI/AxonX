"""Machine component contracts and built-in implementations."""

from .base_machine_component import BaseMachineComponent
from .local_machine_component import (
    LocalMachineComponent,
    platform as platform,
    psutil as psutil,
    shutil as shutil,
    subprocess as subprocess,
)

# Backward-compatible name and module attributes used by existing integrations.
MachineComponent = LocalMachineComponent

__all__ = ["BaseMachineComponent", "LocalMachineComponent", "MachineComponent"]
