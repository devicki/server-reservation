import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.models.reservation import Reservation
from app.database import get_db
from app.models.reservation import ReservationStatus
from app.models.user import User
from app.schemas.reservation import (
    AvailabilityCheckResponse,
    ReservationCreateRequest,
    ReservationListResponse,
    ReservationResponse,
    ReservationUpdateRequest,
)
from app.services.calendar_sync import calendar_sync_service
from app.services.reservation import ReservationService

router = APIRouter(prefix="/reservations", tags=["Reservations"])
logger = logging.getLogger(__name__)


def _to_response(reservation, calendar_synced: bool = False) -> ReservationResponse:
    """Convert reservation model to response, safely handling relationships."""
    data = ReservationResponse.model_validate(reservation)
    data.calendar_synced = calendar_synced or reservation.google_event_id is not None
    return data


@router.get("/check-availability", response_model=AvailabilityCheckResponse)
async def check_availability(
    server_resource_id: uuid.UUID = Query(...),
    start_at: datetime = Query(...),
    end_at: datetime = Query(...),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """Check if a time slot is available for a server resource."""
    available, conflicts = await ReservationService.check_availability(
        db=db,
        server_resource_id=server_resource_id,
        start_at=start_at,
        end_at=end_at,
    )
    return AvailabilityCheckResponse(
        available=available,
        conflicts=[_to_response(c) for c in conflicts],
    )


@router.get("/", response_model=ReservationListResponse)
async def list_reservations(
    server_resource_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    status: ReservationStatus | None = ReservationStatus.ACTIVE,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """List reservations with optional filters."""
    reservations, total = await ReservationService.list_reservations(
        db=db,
        server_resource_id=server_resource_id,
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        status=status,
        limit=limit,
        offset=offset,
    )
    return ReservationListResponse(
        items=[_to_response(r) for r in reservations],
        total=total,
    )


@router.get("/{reservation_id}", response_model=ReservationResponse)
async def get_reservation(
    reservation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """Get a specific reservation."""
    reservation = await ReservationService.get_by_id(db, reservation_id)
    return _to_response(reservation)


@router.post("/", response_model=ReservationResponse, status_code=201)
async def create_reservation(
    body: ReservationCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new reservation. Conflicts are checked atomically."""
    reservation = await ReservationService.create(
        db=db,
        user_id=current_user.id,
        server_resource_id=body.server_resource_id,
        title=body.title,
        description=body.description,
        start_at=body.start_at,
        end_at=body.end_at,
    )

    # Sync to Google Calendar (reservation must have user/server_resource for event title/description)
    calendar_synced = False
    result = await db.execute(
        select(Reservation)
        .options(
            selectinload(Reservation.user),
            selectinload(Reservation.server_resource),
        )
        .where(Reservation.id == reservation.id)
    )
    reservation_loaded = result.scalar_one()
    event_id = await calendar_sync_service.sync_create(reservation_loaded)
    if event_id:
        reservation_loaded.google_event_id = event_id
        await db.commit()
        await db.refresh(reservation_loaded)
        calendar_synced = True
        reservation = reservation_loaded
    else:
        logger.warning(
            "Calendar sync skipped or failed for reservation %s. "
            "Check GOOGLE_CALENDAR_ENABLED, GOOGLE_SERVICE_ACCOUNT_FILE, GOOGLE_CALENDAR_ID and backend logs.",
            reservation.id,
        )

    return _to_response(reservation, calendar_synced=calendar_synced)


@router.put("/{reservation_id}", response_model=ReservationResponse)
async def update_reservation(
    reservation_id: uuid.UUID,
    body: ReservationUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a reservation. Only the owner can update."""
    reservation = await ReservationService.update(
        db=db,
        reservation_id=reservation_id,
        current_user=current_user,
        title=body.title,
        description=body.description,
        start_at=body.start_at,
        end_at=body.end_at,
    )

    # Sync to Google Calendar
    await calendar_sync_service.sync_update(reservation)

    return _to_response(reservation)


@router.delete("/{reservation_id}", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cancel a reservation. Owner or admin can cancel."""
    reservation = await ReservationService.cancel(
        db=db,
        reservation_id=reservation_id,
        current_user=current_user,
    )

    # Sync deletion to Google Calendar
    await calendar_sync_service.sync_delete(reservation)

    return _to_response(reservation)
