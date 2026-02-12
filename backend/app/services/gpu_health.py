"""Collect GPU health from remote servers via SSH (nvidia-smi)."""
import asyncio
import logging
import re
from dataclasses import dataclass

from app.schemas.dashboard import GpuInfo
from app.services.ssh_runner import run_command

logger = logging.getLogger(__name__)


@dataclass
class GpuHealthResult:
    ok: bool
    error_message: str | None
    gpus: list[GpuInfo]

# nvidia-smi CSV: index, name, memory.total, memory.used, memory.free, utilization.gpu, temperature.gpu
# With nounits. GPU name may contain commas, so we parse from the end for numeric fields.
NVIDIA_SMI_CMD = (
    "nvidia-smi --query-gpu=index,name,memory.total,memory.used,memory.free,"
    "utilization.gpu,temperature.gpu --format=csv,noheader,nounits 2>/dev/null || "
    "nvidia-smi --query-gpu=index,name,memory.total,memory.used,memory.free,"
    "utilization.gpu,temperature.gpu --format=csv,noheader 2>/dev/null"
)


def _parse_int_or_none(s: str) -> int | None:
    s = (s or "").strip()
    if not s or s.upper() == "N/A":
        return None
    s = re.sub(r"[^\d-]", "", s)
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _parse_nvidia_smi_csv(stdout: str) -> list[GpuInfo]:
    """Parse nvidia-smi CSV output (noheader,nounits or noheader with units)."""
    gpus: list[GpuInfo] = []
    for line in stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        # index, name, mem_total, mem_used, mem_free, util_pct, temp_c
        # Name might contain commas: take first as index, last 5 as numbers, middle is name.
        if len(parts) < 7:
            continue
        try:
            idx = _parse_int_or_none(parts[0])
            if idx is None:
                idx = len(gpus)
            name = ",".join(parts[1 : -5]).strip() or f"GPU {idx}"
            mem_total = _parse_int_or_none(parts[-5])
            mem_used = _parse_int_or_none(parts[-4])
            mem_free = _parse_int_or_none(parts[-3])
            util_pct = _parse_int_or_none(parts[-2])
            temp_c = _parse_int_or_none(parts[-1])
            gpus.append(
                GpuInfo(
                    index=idx,
                    name=name,
                    memory_total_mib=mem_total,
                    memory_used_mib=mem_used,
                    memory_free_mib=mem_free,
                    utilization_gpu_pct=util_pct,
                    temperature_gpu_c=temp_c,
                )
            )
        except (IndexError, ValueError) as e:
            logger.warning("Failed to parse nvidia-smi line %r: %s", line, e)
            continue
    return gpus


def collect_gpu_health_sync(
    host: str,
    port: int,
    username: str,
    private_key: str | None,
    timeout_sec: float = 15.0,
) -> GpuHealthResult:
    """
    Run nvidia-smi on a remote host via SSH and return GpuHealthResult.
    Sets ok=False and error_message when SSH or command fails.
    """
    if not host or not username or not private_key:
        return GpuHealthResult(
            ok=False,
            error_message="SSH not configured (host, username, or private key missing)",
            gpus=[],
        )
    result = run_command(
        host,
        NVIDIA_SMI_CMD,
        port=port,
        username=username,
        private_key=private_key,
        timeout_sec=timeout_sec,
    )
    if not result.ok:
        logger.warning("nvidia-smi on %s failed: %s", host, result.message)
        return GpuHealthResult(ok=False, error_message=result.message, gpus=[])
    return GpuHealthResult(
        ok=True,
        error_message=None,
        gpus=_parse_nvidia_smi_csv(result.stdout or ""),
    )


async def collect_gpu_health(
    host: str,
    port: int,
    username: str,
    private_key: str | None,
    timeout_sec: float = 15.0,
) -> GpuHealthResult:
    """Async wrapper for collect_gpu_health_sync (run in thread pool)."""
    return await asyncio.to_thread(
        collect_gpu_health_sync,
        host,
        port,
        username,
        private_key,
        timeout_sec,
    )
