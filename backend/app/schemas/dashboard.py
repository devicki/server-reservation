import uuid
from datetime import datetime

from pydantic import BaseModel


class TimelineReservation(BaseModel):
    id: uuid.UUID
    title: str
    user_name: str
    user_id: uuid.UUID
    account_name: str | None = None
    start_at: datetime
    end_at: datetime
    is_mine: bool = False

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
    """GPU health for one server (one host)."""

    server_resource_id: uuid.UUID
    server_name: str
    ok: bool
    error_message: str | None = None
    gpus: list[GpuInfo] = []


class GpuHealthResponse(BaseModel):
    """Response for GET /dashboard/gpu-health."""

    servers: list[ServerGpuHealth]
