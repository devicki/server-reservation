import uuid
from datetime import datetime

from pydantic import BaseModel


class TimelineReservation(BaseModel):
    id: uuid.UUID
    title: str
    user_name: str
    user_id: uuid.UUID
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
