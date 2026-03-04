import uuid
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field, model_validator

from app.config import get_settings
from app.models.reservation import ReservationStatus


def _max_reservation_hours() -> int:
    return get_settings().MAX_RESERVATION_HOURS


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class ReservationCreateRequest(BaseModel):
    server_resource_id: uuid.UUID
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    account_name: str | None = Field(default=None, max_length=100)
    start_at: datetime
    end_at: datetime

    @model_validator(mode="after")
    def validate_time_range(self):
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        if _to_utc(self.start_at) < _now_utc():
            raise ValueError("Reservation start time cannot be in the past")
        max_h = _max_reservation_hours()
        duration = self.end_at - self.start_at
        if duration > timedelta(hours=max_h):
            raise ValueError(f"Reservation duration cannot exceed {max_h} hours")
        return self


class ReservationUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    account_name: str | None = Field(default=None, max_length=100)
    start_at: datetime | None = None
    end_at: datetime | None = None

    @model_validator(mode="after")
    def validate_time_range(self):
        if self.start_at is not None and _to_utc(self.start_at) < _now_utc():
            raise ValueError("Reservation start time cannot be in the past")
        if self.end_at is not None and _to_utc(self.end_at) < _now_utc():
            raise ValueError("Reservation end time cannot be in the past")
        if self.start_at and self.end_at:
            if self.end_at <= self.start_at:
                raise ValueError("end_at must be after start_at")
            max_h = _max_reservation_hours()
            duration = self.end_at - self.start_at
            if duration > timedelta(hours=max_h):
                raise ValueError(f"Reservation duration cannot exceed {max_h} hours")
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


class ReservationInstanceResponse(BaseModel):
    id: uuid.UUID
    start_at: datetime
    end_at: datetime
    status: ReservationStatus

    model_config = {"from_attributes": True}


class ReservationResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    server_resource_id: uuid.UUID
    title: str
    description: str | None
    account_name: str | None = None
    # 단일 예약의 편의 필드: 첫 번째 instance에서 파생 (반복 예약은 None)
    start_at: datetime | None = None
    end_at: datetime | None = None
    status: ReservationStatus
    google_event_id: str | None
    calendar_synced: bool = False
    created_at: datetime
    updated_at: datetime
    user: ReservationUserResponse | None = None
    server_resource: ReservationResourceResponse | None = None
    # 전체 instance 목록 (반복 예약 포함 조회 시 활용)
    instances: list[ReservationInstanceResponse] = []

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def populate_single_times(self):
        """
        단일 예약(is_recurring=False)에서 start_at/end_at이 없을 경우
        첫 번째 instance에서 자동으로 채운다.
        """
        if self.start_at is None and self.instances:
            self.start_at = self.instances[0].start_at
        if self.end_at is None and self.instances:
            self.end_at = self.instances[0].end_at
        return self


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
