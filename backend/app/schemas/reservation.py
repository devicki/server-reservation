import uuid
from datetime import datetime, timedelta

from pydantic import BaseModel, Field, model_validator

from app.models.reservation import ReservationStatus

MAX_RESERVATION_HOURS = 24


class ReservationCreateRequest(BaseModel):
    server_resource_id: uuid.UUID
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    start_at: datetime
    end_at: datetime

    @model_validator(mode="after")
    def validate_time_range(self):
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        duration = self.end_at - self.start_at
        if duration > timedelta(hours=MAX_RESERVATION_HOURS):
            raise ValueError(f"Reservation duration cannot exceed {MAX_RESERVATION_HOURS} hours")
        return self


class ReservationUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None

    @model_validator(mode="after")
    def validate_time_range(self):
        if self.start_at and self.end_at:
            if self.end_at <= self.start_at:
                raise ValueError("end_at must be after start_at")
            duration = self.end_at - self.start_at
            if duration > timedelta(hours=MAX_RESERVATION_HOURS):
                raise ValueError(f"Reservation duration cannot exceed {MAX_RESERVATION_HOURS} hours")
        return self


class ReservationUserResponse(BaseModel):
    id: uuid.UUID
    name: str
    email: str

    model_config = {"from_attributes": True}


class ReservationResourceResponse(BaseModel):
    id: uuid.UUID
    name: str

    model_config = {"from_attributes": True}


class ReservationResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    server_resource_id: uuid.UUID
    title: str
    description: str | None
    start_at: datetime
    end_at: datetime
    status: ReservationStatus
    google_event_id: str | None
    calendar_synced: bool = False
    created_at: datetime
    updated_at: datetime
    user: ReservationUserResponse | None = None
    server_resource: ReservationResourceResponse | None = None

    model_config = {"from_attributes": True}


class ReservationListResponse(BaseModel):
    items: list[ReservationResponse]
    total: int


class AvailabilityCheckRequest(BaseModel):
    server_resource_id: uuid.UUID
    start_at: datetime
    end_at: datetime


class AvailabilityCheckResponse(BaseModel):
    available: bool
    conflicts: list[ReservationResponse] = []
