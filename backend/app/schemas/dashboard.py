import uuid
from datetime import datetime

from pydantic import BaseModel


class TimelineReservation(BaseModel):
    id: uuid.UUID           # ReservationInstance ID (캘린더 이벤트 고유 키)
    reservation_id: uuid.UUID  # 원본 Reservation ID (수정/삭제에 사용)
    title: str
    user_name: str
    user_id: uuid.UUID
    account_name: str | None = None
    start_at: datetime
    end_at: datetime
    is_mine: bool = False
    status: str = "active"  # active | completed | canceled

    model_config = {"from_attributes": True}


class TimelineResource(BaseModel):
    id: uuid.UUID
    name: str
    reservations: list[TimelineReservation] = []


class TimelineResponse(BaseModel):
    resources: list[TimelineResource]


class ResourceStatusEnum(str):
    IN_USE = "in_use"
    RESERVED = "reserved"
    AVAILABLE = "available"


class ResourceStatus(BaseModel):
    id: uuid.UUID
    name: str
    current_status: str
    current_reservation: TimelineReservation | None = None
    next_reservation: TimelineReservation | None = None


class StatusResponse(BaseModel):
    resources: list[ResourceStatus]


# ─── GPU Health ─────────────────────────────────────────────


class GpuProcessInfo(BaseModel):
    """Process using a GPU (from nvidia-smi --query-compute-apps)."""

    gpu_name: str = ""  # e.g. "GPU 0" or "0"
    pid: int = 0
    process_name: str = ""
    used_memory_mib: int | None = None


class GpuInfo(BaseModel):
    """Single GPU metrics from nvidia-smi."""

    index: int
    name: str
    memory_total_mib: int | None = None
    memory_used_mib: int | None = None
    memory_free_mib: int | None = None
    utilization_gpu_pct: int | None = None
    temperature_gpu_c: int | None = None


class ServerGpuHealth(BaseModel):
    """GPU health and usage for one server (one host)."""

    server_resource_id: uuid.UUID
    server_name: str
    ok: bool
    error_message: str | None = None
    gpus: list[GpuInfo] = []
    processes: list[GpuProcessInfo] = []
    recent_serve_cases: list["ServerServeCaseSummary"] = []


class ServerServeCaseSummary(BaseModel):
    """요약: 이 서버에서 공유된 serve 사례 (최근 N건)."""

    id: uuid.UUID
    model_name: str
    serve_command_preview: str = ""
    created_at: datetime


class GpuHealthResponse(BaseModel):
    """Response for GET /dashboard/gpu-health."""

    servers: list[ServerGpuHealth]
