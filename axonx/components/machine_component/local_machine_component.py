"""Local and remote machine resource inspection."""

from __future__ import annotations

import asyncio
import csv
import json
import os
import platform
import shutil
import subprocess
from importlib import metadata
from pathlib import Path
from typing import Any

import psutil

from ..client.http_client import HttpClient
from ..component_registry import R
from .base_machine_component import BaseMachineComponent


@R.register("machine")
class LocalMachineComponent(BaseMachineComponent):
    """Collect local machine resources or read them from another AxonX node."""

    def __init__(self, timeout: float = 10.0, cpu_sample_interval: float = 0.1, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if cpu_sample_interval < 0:
            raise ValueError("cpu_sample_interval must be non-negative")

        self.timeout = timeout
        self.cpu_sample_interval = cpu_sample_interval

    async def get_info(self, address: str | None = None) -> dict[str, Any]:
        """Return local status, or status from one configured remote node."""
        if address is None:
            return await asyncio.to_thread(self._collect_local_info)
        node = next((node for node in self.app_config.remote_nodes if node.address == address), None)
        if node is None:
            raise ValueError(f"Remote AxonX is not configured: {address!r}")
        async with HttpClient(host_ip=node.host_ip, host_port=node.host_port, timeout=self.timeout) as client:
            job_response = await client.run_job("machine_status")
        if not job_response.success or not isinstance(job_response.answer, dict):
            raise ValueError("Remote machine returned an unsuccessful or invalid response")
        return job_response.answer

    def _collect_local_info(self) -> dict[str, Any]:
        cpu_percent = psutil.cpu_percent(interval=self.cpu_sample_interval)
        total_cores = psutil.cpu_count(logical=True) or os.cpu_count() or 0
        memory = psutil.virtual_memory()
        return {
            "axonx": {"version": self._axonx_version(), "git_commit": self._git_commit()},
            "cpu": {
                "total_cores": total_cores,
                # May be unavailable on some virtualized systems.
                "physical_cores": psutil.cpu_count(logical=False),
                "usage_percent": cpu_percent,
                "used_cores": round(total_cores * cpu_percent / 100, 2),
            },
            "memory": {
                "total_bytes": memory.total,
                "used_bytes": memory.used,
                "available_bytes": memory.available,
                "usage_percent": memory.percent,
            },
            "gpus": self._gpu_info(),
        }

    @staticmethod
    def _axonx_version() -> str:
        try:
            return metadata.version("axonx")
        except metadata.PackageNotFoundError:
            from ... import __version__

            return __version__

    @staticmethod
    def _git_commit() -> str | None:
        if commit := os.environ.get("AXONX_GIT_COMMIT"):
            return commit
        package_root = Path(__file__).resolve().parents[3]
        try:
            result = subprocess.run(
                ["git", "-C", str(package_root), "rev-parse", "HEAD"],
                capture_output=True,
                check=True,
                text=True,
                timeout=2,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return result.stdout.strip() or None

    @staticmethod
    def _gpu_info() -> list[dict[str, Any]] | None:
        """Detect NVIDIA on Linux/Windows and AMD ROCm on Linux."""
        # macOS GPU metrics are not exposed through a stable public interface.
        if platform.system() == "Darwin":
            return None

        gpus = []
        if shutil.which("nvidia-smi"):
            gpus.extend(LocalMachineComponent._nvidia_gpu_info())
        if shutil.which("rocm-smi"):
            gpus.extend(LocalMachineComponent._amd_gpu_info())
        return gpus or None

    @staticmethod
    def _number(value, multiplier=1):
        try:
            return float(value) * multiplier
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _nvidia_gpu_info() -> list[dict[str, Any]]:
        fields = "index,uuid,name,memory.total,memory.used,memory.free,utilization.gpu"
        try:
            result = subprocess.run(
                ["nvidia-smi", f"--query-gpu={fields}", "--format=csv,noheader,nounits"],
                capture_output=True,
                check=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            return []

        gpus = []
        for row in csv.reader(result.stdout.splitlines()):
            if len(row) != 7:
                continue
            index, uuid, name, total_mib, used_mib, free_mib, usage = map(str.strip, row)
            gpu_index = LocalMachineComponent._number(index)
            if gpu_index is None:
                continue
            total_bytes = LocalMachineComponent._number(total_mib, 1024**2)
            used_bytes = LocalMachineComponent._number(used_mib, 1024**2)
            free_bytes = LocalMachineComponent._number(free_mib, 1024**2)
            gpus.append(
                {
                    "vendor": "nvidia",
                    "index": int(gpu_index),
                    "uuid": uuid,
                    "name": name,
                    "memory_total_bytes": int(total_bytes) if total_bytes is not None else None,
                    "memory_used_bytes": int(used_bytes) if used_bytes is not None else None,
                    "memory_available_bytes": int(free_bytes) if free_bytes is not None else None,
                    "memory_usage_percent": (
                        round(used_bytes * 100 / total_bytes, 2) if total_bytes and used_bytes is not None else None
                    ),
                    "usage_percent": LocalMachineComponent._number(usage),
                }
            )
        return gpus

    @staticmethod
    def _amd_gpu_info() -> list[dict[str, Any]]:
        try:
            result = subprocess.run(
                ["rocm-smi", "--showproductname", "--showuniqueid", "--showmeminfo", "vram", "--showuse", "--json"],
                capture_output=True,
                check=True,
                text=True,
                timeout=5,
            )
            cards = json.loads(result.stdout)
        except (OSError, subprocess.SubprocessError, ValueError):
            return []
        if not isinstance(cards, dict):
            return []

        gpus = []
        for fallback_index, (card, values) in enumerate(cards.items()):
            if not isinstance(card, str) or not isinstance(values, dict):
                continue
            total_bytes = LocalMachineComponent._number(values.get("VRAM Total Memory (B)"))
            used_bytes = LocalMachineComponent._number(values.get("VRAM Total Used Memory (B)"))
            card_index = card.removeprefix("card")
            index = int(card_index) if card_index.isdigit() else fallback_index
            gpus.append(
                {
                    "vendor": "amd",
                    "index": index,
                    "uuid": values.get("Unique ID"),
                    "name": values.get("Card series") or values.get("Card model"),
                    "memory_total_bytes": int(total_bytes) if total_bytes is not None else None,
                    "memory_used_bytes": int(used_bytes) if used_bytes is not None else None,
                    "memory_available_bytes": (
                        int(total_bytes - used_bytes) if total_bytes is not None and used_bytes is not None else None
                    ),
                    "memory_usage_percent": (
                        round(used_bytes * 100 / total_bytes, 2) if total_bytes and used_bytes is not None else None
                    ),
                    "usage_percent": LocalMachineComponent._number(values.get("GPU use (%)")),
                }
            )
        return gpus
