"""Machine resource collection tests."""

import json
import subprocess
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from axonx.steps.machine.contracts import CpuInfo, GpuInfo, MemoryInfo
from axonx.steps.machine.gpu import (
    MIB_BYTES,
    GpuCollection,
    collect_gpus,
    parse_nvidia_output,
    parse_rocm_output,
)
from axonx.steps.machine.metrics import (
    collect_cpu,
    collect_machine_info,
    collect_memory,
)
from axonx.steps.machine.steps import MachineStatusStep


def test_parse_nvidia_output():
    devices = parse_nvidia_output(
        '0, GPU-1, "NVIDIA A100, PCIe", 81920, 40960, 40960, 75\n'
    )

    assert [device.model_dump() for device in devices] == [
        {
            "vendor": "nvidia",
            "index": 0,
            "uuid": "GPU-1",
            "name": "NVIDIA A100, PCIe",
            "memory_total_bytes": 81920 * MIB_BYTES,
            "memory_used_bytes": 40960 * MIB_BYTES,
            "memory_available_bytes": 40960 * MIB_BYTES,
            "memory_usage_percent": 50.0,
            "usage_percent": 75.0,
        },
    ]


def test_nvidia_parser_ignores_bad_identity_and_discards_bad_metrics():
    output = "\n".join(
        (
            "nan, GPU-bad, Bad, 100, 50, 50, 10",
            "1.5, GPU-fraction, Bad, 100, 50, 50, 10",
            "2, GPU-ok, Good, inf, -1, nan, 101",
        ),
    )

    assert [device.model_dump() for device in parse_nvidia_output(output)] == [
        {
            "vendor": "nvidia",
            "index": 2,
            "uuid": "GPU-ok",
            "name": "Good",
            "memory_total_bytes": None,
            "memory_used_bytes": None,
            "memory_available_bytes": None,
            "memory_usage_percent": None,
            "usage_percent": None,
        },
    ]


def test_parse_rocm_output():
    output = json.dumps(
        {
            "card0": {
                "Card series": "AMD Radeon PRO",
                "Unique ID": "GPU-AMD-1",
                "VRAM Total Memory (B)": "1000",
                "VRAM Total Used Memory (B)": "250",
                "GPU use (%)": "40",
            },
        },
    )

    assert parse_rocm_output(output)[0].model_dump() == {
        "vendor": "amd",
        "index": 0,
        "uuid": "GPU-AMD-1",
        "name": "AMD Radeon PRO",
        "memory_total_bytes": 1000,
        "memory_used_bytes": 250,
        "memory_available_bytes": 750,
        "memory_usage_percent": 25.0,
        "usage_percent": 40.0,
    }


@pytest.mark.parametrize("output", ("not-json", "[]"))
def test_rocm_parser_rejects_invalid_document(output):
    with pytest.raises(ValueError):
        parse_rocm_output(output)


def test_collection_uses_discovered_path_and_preserves_failures(monkeypatch):
    monkeypatch.setattr("axonx.steps.machine.gpu.platform.system", lambda: "Linux")
    monkeypatch.setattr(
        "axonx.steps.machine.gpu.shutil.which",
        lambda command: f"/vendor/{command}",
    )

    def run(command, **kwargs):
        assert command[0].startswith("/vendor/")
        if command[0].endswith("nvidia-smi"):
            raise subprocess.TimeoutExpired(command, 5)
        return SimpleNamespace(stdout="{}")

    monkeypatch.setattr("axonx.steps.machine.gpu.subprocess.run", run)

    result = collect_gpus()

    assert result.devices == ()
    assert len(result.warnings) == 1
    assert "nvidia-smi" in result.warnings[0]
    assert "timed out" in result.warnings[0]


def test_collect_cpu_and_memory(monkeypatch):
    monkeypatch.setattr(
        "axonx.steps.machine.metrics.psutil.cpu_count",
        lambda logical: 8 if logical else 4,
    )
    monkeypatch.setattr(
        "axonx.steps.machine.metrics.psutil.cpu_percent", lambda interval: 25.0
    )
    monkeypatch.setattr(
        "axonx.steps.machine.metrics.psutil.virtual_memory",
        lambda: SimpleNamespace(total=1_000, used=400, available=550, percent=45.0),
    )

    assert collect_cpu(0).model_dump() == {
        "total_cores": 8,
        "physical_cores": 4,
        "usage_percent": 25.0,
    }
    assert collect_memory().model_dump() == {
        "total_bytes": 1_000,
        "used_bytes": 400,
        "available_bytes": 550,
        "usage_percent": 45.0,
    }


def test_machine_status_step_rejects_unknown_options():
    with pytest.raises(TypeError, match="cpu_sample_intervl"):
        MachineStatusStep(cpu_sample_intervl=0)


def test_gpu_schema_rejects_invalid_metrics():
    with pytest.raises(ValidationError):
        GpuInfo(vendor="nvidia", index=0, usage_percent=float("nan"))
    with pytest.raises(ValidationError, match="memory_used_bytes"):
        GpuInfo(vendor="amd", index=0, memory_total_bytes=10, memory_used_bytes=11)


def test_no_gpu_is_an_empty_list(monkeypatch):
    step = MachineStatusStep(cpu_sample_interval=0)
    monkeypatch.setattr(
        "axonx.steps.machine.metrics.get_build_info",
        lambda: type(
            "BuildInfo",
            (),
            {"version": "1.2.3", "git_commit": None, "git_branch": None},
        )(),
    )
    monkeypatch.setattr(
        "axonx.steps.machine.metrics.collect_cpu",
        lambda _: CpuInfo(total_cores=1, physical_cores=1, usage_percent=0),
    )
    monkeypatch.setattr(
        "axonx.steps.machine.metrics.collect_memory",
        lambda: MemoryInfo(
            total_bytes=1, used_bytes=0, available_bytes=1, usage_percent=0
        ),
    )
    monkeypatch.setattr(
        "axonx.steps.machine.metrics.collect_gpus", lambda: GpuCollection()
    )

    assert collect_machine_info(step.cpu_sample_interval, step.logger).gpus == []
