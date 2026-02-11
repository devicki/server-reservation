import logging
import uuid
from datetime import datetime, timedelta, timezone

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models.reservation import Reservation, ReservationStatus
from app.models.server_resource import ServerResource
from app.models.user import User, UserRole
from app.schemas.reservation import MAX_RESERVATION_HOURS
from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class ReservationService:
    @staticmethod
    async def create(
        db: AsyncSession,
        user_id: uuid.UUID,
        server_resource_id: uuid.UUID,
        title: str,
        start_at: datetime,
        end_at: datetime,
        description: str | None = None,
    ) -> Reservation:
        """Create a reservation with conflict check using SELECT FOR UPDATE."""
        # Verify the server resource exists and is active
        result = await db.execute(
            select(ServerResource).where(
                ServerResource.id == server_resource_id,
                ServerResource.is_active.is_(True),
            )
        )
        resource = result.scalar_one_or_none()
        if resource is None:
            raise NotFoundError("Server resource not found or inactive")

        # Application-level conflict check with row locking
        conflict_stmt = (
            select(Reservation)
            .where(
                Reservation.server_resource_id == server_resource_id,
                Reservation.status == ReservationStatus.ACTIVE,
                Reservation.start_at < end_at,
                Reservation.end_at > start_at,
            )
            .with_for_update()
        )
        result = await db.execute(conflict_stmt)
        conflicts = result.scalars().all()

        if conflicts:
            raise ConflictError(
                f"Time slot conflicts with {len(conflicts)} existing reservation(s)"
            )

        reservation = Reservation(
            user_id=user_id,
            server_resource_id=server_resource_id,
            title=title,
            description=description,
            start_at=start_at,
            end_at=end_at,
        )
        db.add(reservation)

        try:
            await db.commit()
            await db.refresh(reservation)
        except IntegrityError:
            await db.rollback()
            raise ConflictError("Time slot already reserved (concurrent request)")

        return reservation

    @staticmethod
    async def get_by_id(db: AsyncSession, reservation_id: uuid.UUID) -> Reservation:
        """Get a reservation by ID."""
        result = await db.execute(
            select(Reservation).where(Reservation.id == reservation_id)
        )
        reservation = result.scalar_one_or_none()
        if reservation is None:
            raise NotFoundError("Reservation not found")
        return reservation

    @staticmethod
    async def list_reservations(
        db: AsyncSession,
        server_resource_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        status: ReservationStatus | None = ReservationStatus.ACTIVE,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Reservation], int]:
        """List reservations with filters."""
        conditions = []

        if server_resource_id:
            conditions.append(Reservation.server_resource_id == server_resource_id)
        if user_id:
            conditions.append(Reservation.user_id == user_id)
        if start_date:
            conditions.append(Reservation.end_at > start_date)
        if end_date:
            conditions.append(Reservation.start_at < end_date)
        if status:
            conditions.append(Reservation.status == status)

        # Count
        count_stmt = select(func.count(Reservation.id)).where(*conditions)
        total = (await db.execute(count_stmt)).scalar()

        # Query
        stmt = (
            select(Reservation)
            .where(*conditions)
            .order_by(Reservation.start_at)
            .limit(limit)
            .offset(offset)
        )
        result = await db.execute(stmt)
        reservations = list(result.scalars().all())

        return reservations, total

    @staticmethod
    async def update(
        db: AsyncSession,
        reservation_id: uuid.UUID,
        current_user: User,
        title: str | None = None,
        description: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> Reservation:
        """Update a reservation. Only the owner can update."""
        reservation = await ReservationService.get_by_id(db, reservation_id)

        if reservation.user_id != current_user.id:
            raise ForbiddenError("You can only modify your own reservations")

        if reservation.status == ReservationStatus.CANCELED:
            raise ConflictError("Cannot modify a canceled reservation")

        if reservation.end_at < datetime.now(timezone.utc):
            raise ForbiddenError("Past schedules cannot be modified.")

        # If time is being changed, check for conflicts
        new_start = start_at or reservation.start_at
        new_end = end_at or reservation.end_at

        if new_end <= new_start:
            raise ConflictError("end_at must be after start_at")
        if (new_end - new_start) > timedelta(hours=MAX_RESERVATION_HOURS):
            raise ConflictError(
                f"Reservation duration cannot exceed {MAX_RESERVATION_HOURS} hours"
            )

        if start_at or end_at:
            conflict_stmt = (
                select(Reservation)
                .where(
                    Reservation.server_resource_id == reservation.server_resource_id,
                    Reservation.status == ReservationStatus.ACTIVE,
                    Reservation.id != reservation_id,
                    Reservation.start_at < new_end,
                    Reservation.end_at > new_start,
                )
                .with_for_update()
            )
            result = await db.execute(conflict_stmt)
            conflicts = result.scalars().all()

            if conflicts:
                raise ConflictError(
                    f"Time slot conflicts with {len(conflicts)} existing reservation(s)"
                )

        # Apply updates
        if title is not None:
            reservation.title = title
        if description is not None:
            reservation.description = description
        if start_at is not None:
            reservation.start_at = start_at
        if end_at is not None:
            reservation.end_at = end_at

        try:
            await db.commit()
            await db.refresh(reservation)
        except IntegrityError:
            await db.rollback()
            raise ConflictError("Time slot already reserved (concurrent request)")

        return reservation

    @staticmethod
    async def cancel(
        db: AsyncSession,
        reservation_id: uuid.UUID,
        current_user: User,
    ) -> Reservation:
        """Cancel a reservation. Owner or admin can cancel."""
        reservation = await ReservationService.get_by_id(db, reservation_id)

        if (
            reservation.user_id != current_user.id
            and current_user.role != UserRole.ADMIN
        ):
            raise ForbiddenError("You can only cancel your own reservations")

        if reservation.status == ReservationStatus.CANCELED:
            raise ConflictError("Reservation is already canceled")

        if reservation.end_at < datetime.now(timezone.utc):
            raise ForbiddenError("Past schedules cannot be deleted.")

        reservation.status = ReservationStatus.CANCELED
        await db.commit()
        await db.refresh(reservation)

        return reservation

    @staticmethod
    async def check_availability(
        db: AsyncSession,
        server_resource_id: uuid.UUID,
        start_at: datetime,
        end_at: datetime,
    ) -> tuple[bool, list[Reservation]]:
        """Check if a time slot is available."""
        stmt = select(Reservation).where(
            Reservation.server_resource_id == server_resource_id,
            Reservation.status == ReservationStatus.ACTIVE,
            Reservation.start_at < end_at,
            Reservation.end_at > start_at,
        )
        result = await db.execute(stmt)
        conflicts = list(result.scalars().all())

        return len(conflicts) == 0, conflicts
