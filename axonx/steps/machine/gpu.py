"""Discover GPUs and parse metrics reported by vendor command-line tools."""

from __future__ import annotations

import csv
import json
import math
import platform
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from .contracts import GpuInfo

NVIDIA_COLUMNS = (
    "index",
    "uuid",
    "name",
    "memory.total",
    "memory.used",
    "memory.free",
    "utilization.gpu",
)
MIB_BYTES = 1024**2
TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class GpuCollection:
    """GPU devices plus non-fatal problems encountered while discovering them."""

    devices: tuple[GpuInfo, ...] = ()
    warnings: tuple[str, ...] = ()


def collect_gpus() -> GpuCollection:
    """Return every GPU reported by installed vendor tools.

    A missing tool simply means that vendor has nothing to report. An installed
    tool that fails is recorded as a warning and does not hide devices returned
    by another vendor.
    """
    if platform.system() == "Darwin":
        return GpuCollection()

    devices: list[GpuInfo] = []
    warnings: list[str] = []
    probes: tuple[tuple[str, Sequence[str], Callable[[str], list[GpuInfo]]], ...] = (
        (
            "nvidia-smi",
            (
                f"--query-gpu={','.join(NVIDIA_COLUMNS)}",
                "--format=csv,noheader,nounits",
            ),
            parse_nvidia_output,
        ),
        (
            "rocm-smi",
            (
                "--showproductname",
                "--showuniqueid",
                "--showmeminfo",
                "vram",
                "--showuse",
                "--json",
            ),
            parse_rocm_output,
        ),
    )
    for executable, arguments, parser in probes:
        path = shutil.which(executable)
        if path is None:
            continue
        output, error = _run(path, *arguments)
        if error is not None:
            warnings.append(f"Unable to collect GPU metrics with {executable}: {error}")
            continue
        try:
            devices.extend(parser(output))
        except ValueError as exc:
            warnings.append(f"Unable to parse GPU metrics from {executable}: {exc}")

    return GpuCollection(tuple(devices), tuple(warnings))


def parse_nvidia_output(output: str) -> list[GpuInfo]:
    """Parse ``nvidia-smi`` CSV output, ignoring malformed device rows."""
    devices: list[GpuInfo] = []
    for row in csv.reader(output.splitlines(), skipinitialspace=True):
        if len(row) != len(NVIDIA_COLUMNS):
            continue
        index, uuid, name, total, used, available, usage = (
            value.strip() for value in row
        )
        parsed_index = _non_negative_int(index)
        if parsed_index is None:
            continue
        devices.append(
            _gpu(
                vendor="nvidia",
                index=parsed_index,
                uuid=uuid or None,
                name=name or None,
                memory_total_bytes=_byte_count(total, MIB_BYTES),
                memory_used_bytes=_byte_count(used, MIB_BYTES),
                memory_available_bytes=_byte_count(available, MIB_BYTES),
                usage_percent=_percent(usage),
            ),
        )
    if output.strip() and not devices:
        raise ValueError("no valid device rows")
    return devices


def parse_rocm_output(output: str) -> list[GpuInfo]:
    """Parse ``rocm-smi`` JSON output, ignoring malformed device entries."""
    try:
        cards = json.loads(output)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid JSON") from exc
    if not isinstance(cards, dict):
        raise ValueError("expected a JSON object")

    devices: list[GpuInfo] = []
    for card, values in cards.items():
        if not isinstance(card, str) or not isinstance(values, dict):
            continue
        index = _card_index(card)
        if index is None:
            continue
        devices.append(
            _gpu(
                vendor="amd",
                index=index,
                uuid=_optional_string(values.get("Unique ID")),
                name=_optional_string(
                    values.get("Card series") or values.get("Card model")
                ),
                memory_total_bytes=_byte_count(values.get("VRAM Total Memory (B)")),
                memory_used_bytes=_byte_count(values.get("VRAM Total Used Memory (B)")),
                usage_percent=_percent(values.get("GPU use (%)")),
            ),
        )
    return devices


def _gpu(
    *,
    vendor: Literal["nvidia", "amd"],
    index: int,
    uuid: str | None,
    name: str | None,
    memory_total_bytes: int | None,
    memory_used_bytes: int | None,
    usage_percent: float | None,
    memory_available_bytes: int | None = None,
) -> GpuInfo:
    """Build one validated GPU payload and derive consistent memory metrics."""
    if (
        memory_total_bytes is not None
        and memory_used_bytes is not None
        and memory_used_bytes > memory_total_bytes
    ):
        memory_used_bytes = None
    memory_is_consistent = (
        memory_total_bytes is not None
        and memory_used_bytes is not None
        and memory_used_bytes <= memory_total_bytes
    )
    if memory_available_bytes is None and memory_is_consistent:
        memory_available_bytes = memory_total_bytes - memory_used_bytes
    if memory_available_bytes is not None and memory_total_bytes is not None:
        if memory_available_bytes > memory_total_bytes:
            memory_available_bytes = None
    memory_usage_percent = None
    if memory_is_consistent and memory_total_bytes:
        memory_usage_percent = round(memory_used_bytes * 100 / memory_total_bytes, 2)

    return GpuInfo(
        vendor=vendor,
        index=index,
        uuid=uuid,
        name=name,
        memory_total_bytes=memory_total_bytes,
        memory_used_bytes=memory_used_bytes,
        memory_available_bytes=memory_available_bytes,
        memory_usage_percent=memory_usage_percent,
        usage_percent=usage_percent,
    )


def _run(*command: str) -> tuple[str, str | None]:
    """Run a vendor tool and return output plus a concise non-fatal error."""
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            check=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return "", f"timed out after {TIMEOUT_SECONDS:g}s"
    except subprocess.CalledProcessError as exc:
        detail = " ".join((exc.stderr or "").splitlines())[:300]
        return "", f"exited with status {exc.returncode}" + (
            f": {detail}" if detail else ""
        )
    except OSError as exc:
        return "", str(exc)
    return result.stdout, None


def _finite_number(value: object) -> float | None:
    """Parse a finite numeric vendor value."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _non_negative_int(value: object) -> int | None:
    """Parse a non-negative integer without silently truncating it."""
    number = _finite_number(value)
    if number is None or number < 0 or not number.is_integer():
        return None
    return int(number)


def _byte_count(value: object, scale: int = 1) -> int | None:
    """Parse a non-negative byte quantity and convert its reported unit."""
    number = _finite_number(value)
    if number is None or number < 0:
        return None
    return int(number * scale)


def _percent(value: object) -> float | None:
    """Parse a percentage in the inclusive range 0 through 100."""
    number = _finite_number(value)
    return number if number is not None and 0 <= number <= 100 else None


def _card_index(card: str) -> int | None:
    """Read the numeric index from a ROCm card key such as ``card0``."""
    if not card.startswith("card"):
        return None
    return _non_negative_int(card.removeprefix("card"))


def _optional_string(value: object) -> str | None:
    """Return a non-empty string without coercing unexpected JSON values."""
    return value if isinstance(value, str) and value else None
