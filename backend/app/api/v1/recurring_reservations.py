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
