"""Component contract for machine observation, diagnostics and Python execution."""

from abc import ABC, abstractmethod

from ..base import BaseComponent
from .models import MachineDiagnostics, MachineHealth, MachineInfo, PythonOutput


class BaseMachineComponent(BaseComponent, ABC):
    """Expose machine capabilities through the managed component lifecycle."""

    component_type = "machine"

    @abstractmethod
    async def status(self) -> MachineInfo:
        """Sample machine resources and return the running build identity."""

    @abstractmethod
    async def diagnose(self) -> MachineDiagnostics:
        """Inspect runtime, workspace and credential availability without writing files."""

    @abstractmethod
    async def list_machines(self) -> list[MachineHealth]:
        """Check configured targets concurrently and return them in configuration order."""

    @abstractmethod
    async def run_python(self, code: str, timeout: float = 30) -> PythonOutput:
        """Execute Python with bounded output and clean up its process group before returning."""
