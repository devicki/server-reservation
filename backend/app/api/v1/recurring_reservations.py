"""반복 예약 API 엔드포인트"""
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.database import get_db
from app.models.reservation import Reservation
from app.models.reservation_instance import ReservationInstance
from app.models.user import User
from app.schemas.reservation import ReservationResponse
from app.services.recurring_reservation import (
    RecurrenceSpec,
    RecurringReservationService,
)
from pydantic import BaseModel, Field

router = APIRouter(prefix="/reservations/recurring", tags=["Recurring Reservations"])
logger = logging.getLogger(__name__)


class RecurrenceSpecRequest(BaseModel):
    freq: str = Field(..., description="DAILY | WEEKLY | MONTHLY")
    interval: int = Field(default=1, ge=1)
    by_day: str | None = Field(default=None, description="WEEKLY: 'MON,WED,FRI'")
    by_month_day: int | None = Field(default=None, description="MONTHLY: 15")


class RecurringReservationCreateRequest(BaseModel):
    server_resource_id: uuid.UUID
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    account_name: str | None = Field(default=None, max_length=100)
    start_at: datetime
    end_at: datetime
    recurrence: RecurrenceSpecRequest
    recurrence_end_date: datetime | None = None


class RecurringInstanceUpdateRequest(BaseModel):
    """이 일정만 수정"""
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    account_name: str | None = Field(default=None, max_length=100)
    start_at: datetime | None = None
    end_at: datetime | None = None


class RecurringFromUpdateRequest(BaseModel):
    """이 일정부터 이후 모두 수정"""
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    account_name: str | None = Field(default=None, max_length=100)
    start_time: str | None = Field(default=None, description="HH:MM 형식의 시작 시각")
    end_time: str | None = Field(default=None, description="HH:MM 형식의 종료 시각")


class RecurringUpdateResponse(BaseModel):
    updated_count: int
    reservation: ReservationResponse


async def _load_with_instances(db, reservation_id: uuid.UUID) -> Reservation:
    result = await db.execute(
        select(Reservation)
        .options(
            selectinload(Reservation.instances),
            selectinload(Reservation.user),
            selectinload(Reservation.server_resource),
        )
        .where(Reservation.id == reservation_id)
    )
    return result.scalar_one()


@router.post("/", response_model=ReservationResponse, status_code=201)
async def create_recurring_reservation(
    body: RecurringReservationCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """반복 예약 생성."""
    spec = RecurrenceSpec(
        freq=body.recurrence.freq,  # type: ignore[arg-type]
        interval=body.recurrence.interval,
        by_day=body.recurrence.by_day,
        by_month_day=body.recurrence.by_month_day,
    )

    reservation, _ = await RecurringReservationService.create_recurring(
        db=db,
        user_id=current_user.id,
        server_resource_id=body.server_resource_id,
        title=body.title,
        description=body.description,
        account_name=body.account_name,
        start_at=body.start_at,
        end_at=body.end_at,
        spec=spec,
        recurrence_end_date=body.recurrence_end_date,
    )

    return ReservationResponse.model_validate(
        await _load_with_instances(db, reservation.id)
    )


@router.put("/instances/{instance_id}", response_model=ReservationResponse)
async def update_recurring_instance(
    instance_id: uuid.UUID,
    body: RecurringInstanceUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """반복 예약 중 이 일정만 수정."""
    instance = await RecurringReservationService.update_instance(
        db=db,
        instance_id=instance_id,
        current_user=current_user,
        title=body.title,
        description=body.description,
        account_name=body.account_name,
        start_at=body.start_at,
        end_at=body.end_at,
    )
    return ReservationResponse.model_validate(
        await _load_with_instances(db, instance.reservation_id)
    )


@router.put("/instances/{instance_id}/from", response_model=RecurringUpdateResponse)
async def update_recurring_from(
    instance_id: uuid.UUID,
    body: RecurringFromUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """반복 예약 중 이 일정부터 이후 모든 일정 수정."""
    reservation, updated_count = await RecurringReservationService.update_from(
        db=db,
        instance_id=instance_id,
        current_user=current_user,
        title=body.title,
        description=body.description,
        account_name=body.account_name,
        start_time_hhmm=body.start_time,
        end_time_hhmm=body.end_time,
    )
    return RecurringUpdateResponse(
        updated_count=updated_count,
        reservation=ReservationResponse.model_validate(
            await _load_with_instances(db, reservation.id)
        ),
    )


class RecurringCancelResponse(BaseModel):
    cancelled_count: int
    reservation: ReservationResponse


@router.delete("/instances/{instance_id}", response_model=RecurringCancelResponse)
async def cancel_recurring_instance(
    instance_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """반복 예약 중 이 일정만 취소. 남은 일정이 없으면 예약 전체도 취소."""
    instance, reservation = await RecurringReservationService.cancel_instance(
        db=db,
        instance_id=instance_id,
        current_user=current_user,
    )
    return RecurringCancelResponse(
        cancelled_count=1,
        reservation=ReservationResponse.model_validate(
            await _load_with_instances(db, reservation.id)
        ),
    )


@router.delete("/instances/{instance_id}/from", response_model=RecurringCancelResponse)
async def cancel_recurring_from(
    instance_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """반복 예약 중 이 일정부터 이후 모든 일정 취소."""
    reservation, cancelled_count = await RecurringReservationService.cancel_from(
        db=db,
        instance_id=instance_id,
        current_user=current_user,
    )
    return RecurringCancelResponse(
        cancelled_count=cancelled_count,
        reservation=ReservationResponse.model_validate(
            await _load_with_instances(db, reservation.id)
        ),
    )
