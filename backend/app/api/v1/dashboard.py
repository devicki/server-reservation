import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.reservation import Reservation, ReservationStatus
from app.models.server_resource import ServerResource
from app.models.user import User
from app.schemas.dashboard import (
    ResourceStatus,
    StatusResponse,
    TimelineReservation,
    TimelineResource,
    TimelineResponse,
)
from app.schemas.reservation import ReservationListResponse, ReservationResponse

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/timeline", response_model=TimelineResponse)
async def get_timeline(
    start_date: datetime = Query(...),
    end_date: datetime = Query(...),
    server_resource_ids: list[uuid.UUID] | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a timeline view of reservations grouped by server resource."""
    # Get active resources
    resource_conditions = [ServerResource.is_active.is_(True)]
    if server_resource_ids:
        resource_conditions.append(ServerResource.id.in_(server_resource_ids))

    resources_result = await db.execute(
        select(ServerResource)
        .where(*resource_conditions)
        .order_by(ServerResource.name)
    )
    resources = list(resources_result.scalars().all())

    # Get reservations in the time range
    res_result = await db.execute(
        select(Reservation)
        .where(
            Reservation.status == ReservationStatus.ACTIVE,
            Reservation.start_at < end_date,
            Reservation.end_at > start_date,
            Reservation.server_resource_id.in_([r.id for r in resources])
            if resources
            else True,
        )
        .order_by(Reservation.start_at)
    )
    reservations = list(res_result.scalars().all())

    # Group by resource
    reservation_map: dict[uuid.UUID, list[TimelineReservation]] = {}
    for res in reservations:
        timeline_res = TimelineReservation(
            id=res.id,
            title=res.title,
            user_name=res.user.name if res.user else "Unknown",
            user_id=res.user_id,
            start_at=res.start_at,
            end_at=res.end_at,
            is_mine=res.user_id == current_user.id,
        )
        reservation_map.setdefault(res.server_resource_id, []).append(timeline_res)

    timeline_resources = [
        TimelineResource(
            id=r.id,
            name=r.name,
            reservations=reservation_map.get(r.id, []),
        )
        for r in resources
    ]

    return TimelineResponse(resources=timeline_resources)


@router.get("/my-reservations", response_model=ReservationListResponse)
async def get_my_reservations(
    status: ReservationStatus | None = ReservationStatus.ACTIVE,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the current user's reservations."""
    from app.services.reservation import ReservationService

    reservations, total = await ReservationService.list_reservations(
        db=db,
        user_id=current_user.id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return ReservationListResponse(
        items=[ReservationResponse.model_validate(r) for r in reservations],
        total=total,
    )


@router.get("/status", response_model=StatusResponse)
async def get_server_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the current status of all active server resources."""
    now = datetime.now(timezone.utc)

    # Get all active resources
    resources_result = await db.execute(
        select(ServerResource)
        .where(ServerResource.is_active.is_(True))
        .order_by(ServerResource.name)
    )
    resources = list(resources_result.scalars().all())

    statuses = []
    for resource in resources:
        # Current reservation (now is between start and end)
        current_result = await db.execute(
            select(Reservation)
            .where(
                Reservation.server_resource_id == resource.id,
                Reservation.status == ReservationStatus.ACTIVE,
                Reservation.start_at <= now,
                Reservation.end_at > now,
            )
            .limit(1)
        )
        current_reservation = current_result.scalar_one_or_none()

        # Next upcoming reservation
        next_result = await db.execute(
            select(Reservation)
            .where(
                Reservation.server_resource_id == resource.id,
                Reservation.status == ReservationStatus.ACTIVE,
                Reservation.start_at > now,
            )
            .order_by(Reservation.start_at)
            .limit(1)
        )
        next_reservation = next_result.scalar_one_or_none()

        # Determine status
        if current_reservation:
            current_status = "in_use"
        elif next_reservation:
            current_status = "reserved"
        else:
            current_status = "available"

        def _to_timeline(r: Reservation | None) -> TimelineReservation | None:
            if r is None:
                return None
            return TimelineReservation(
                id=r.id,
                title=r.title,
                user_name=r.user.name if r.user else "Unknown",
                user_id=r.user_id,
                start_at=r.start_at,
                end_at=r.end_at,
                is_mine=r.user_id == current_user.id,
            )

        statuses.append(
            ResourceStatus(
                id=resource.id,
                name=resource.name,
                current_status=current_status,
                current_reservation=_to_timeline(current_reservation),
                next_reservation=_to_timeline(next_reservation),
            )
        )

    return StatusResponse(resources=statuses)
