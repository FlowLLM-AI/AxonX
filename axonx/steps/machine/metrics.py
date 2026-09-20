"""Collect local machine metrics outside the asynchronous event loop."""

import psutil

from ...utils.build_info import get_build_info
from .contracts import AxonxInfo, CpuInfo, MachineInfo, MemoryInfo
from .gpu import collect_gpus


def collect_machine_info(sample_interval: float, logger) -> MachineInfo:
    build = get_build_info()
    gpu_collection = collect_gpus()
    for warning in gpu_collection.warnings:
        logger.warning(warning)
    return MachineInfo(
        axonx=AxonxInfo(
            version=build.version,
            git_commit=build.git_commit,
            git_branch=build.git_branch,
        ),
        cpu=collect_cpu(sample_interval),
        memory=collect_memory(),
        gpus=list(gpu_collection.devices),
    )


def collect_cpu(sample_interval: float) -> CpuInfo:
    return CpuInfo(
        total_cores=psutil.cpu_count(logical=True),
        physical_cores=psutil.cpu_count(logical=False),
        usage_percent=psutil.cpu_percent(interval=sample_interval),
    )


def collect_memory() -> MemoryInfo:
    memory = psutil.virtual_memory()
    return MemoryInfo(
        total_bytes=memory.total,
        used_bytes=memory.used,
        available_bytes=memory.available,
        usage_percent=memory.percent,
    )
