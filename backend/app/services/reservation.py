"""단일 예약 서비스

단일/반복 구분 없이 시간 정보는 reservation_instances 테이블에서만 관리한다.
reservations 테이블은 논리 예약(제목, 사용자, 서버, 상태 등)만 보유한다.

중복 검사는 DB EXCLUDE 제약(no_overlap_per_server)에 완전히 위임한다.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.models.reservation import Reservation, ReservationStatus
from app.models.reservation_instance import ReservationInstance
from app.models.server_resource import ServerResource
from app.models.user import User, UserRole
from app.services.recurring_reservation import _raise_conflict_from_integrity_error

logger = logging.getLogger(__name__)


class ReservationService:

    # ------------------------------------------------------------------ #
    # 생성
    # ------------------------------------------------------------------ #

    @staticmethod
    async def create(
        db: AsyncSession,
        user_id: uuid.UUID,
        server_resource_id: uuid.UUID,
        title: str,
        start_at: datetime,
        end_at: datetime,
        description: str | None = None,
        account_name: str | None = None,
    ) -> Reservation:
        """
        단일 예약 생성.

        Reservation(논리) + ReservationInstance(시간) 1개를 함께 생성한다.
        시간 충돌 방지는 DB EXCLUDE 제약에 위임한다.
        """
        now = datetime.now(timezone.utc)
        start_utc = start_at.astimezone(timezone.utc)
        end_utc = end_at.astimezone(timezone.utc)

        if start_utc < now:
            raise BadRequestError("Reservation start time cannot be in the past")
        if end_utc <= start_utc:
            raise BadRequestError("end_at must be after start_at")

        max_hours = get_settings().MAX_RESERVATION_HOURS
        if (end_utc - start_utc) > timedelta(hours=max_hours):
            raise BadRequestError(
                f"Reservation duration cannot exceed {max_hours} hours"
            )

        result = await db.execute(
            select(ServerResource).where(
                ServerResource.id == server_resource_id,
                ServerResource.is_active.is_(True),
            )
        )
        if result.scalar_one_or_none() is None:
            raise NotFoundError("Server resource not found or inactive")

        reservation = Reservation(
            user_id=user_id,
            server_resource_id=server_resource_id,
            title=title,
            description=description,
            account_name=account_name,
            status=ReservationStatus.ACTIVE,
        )
        db.add(reservation)
        await db.flush()

        instance = ReservationInstance(
            reservation_id=reservation.id,
            server_resource_id=server_resource_id,
            start_at=start_at,
            end_at=end_at,
            status=ReservationStatus.ACTIVE,
        )
        db.add(instance)

        try:
            await db.commit()
            await db.refresh(reservation)
        except IntegrityError as exc:
            await db.rollback()
            _raise_conflict_from_integrity_error(exc)

        return reservation

    # ------------------------------------------------------------------ #
    # 조회
    # ------------------------------------------------------------------ #

    @staticmethod
    async def get_by_id(db: AsyncSession, reservation_id: uuid.UUID) -> Reservation:
        result = await db.execute(
            select(Reservation).where(Reservation.id == reservation_id)
        )
        reservation = result.scalar_one_or_none()
        if reservation is None:
            raise NotFoundError("Reservation not found")
        return reservation

    @staticmethod
    async def _get_single_instance(
        db: AsyncSession, reservation_id: uuid.UUID
    ) -> ReservationInstance | None:
        """단일 예약의 instance를 반환 (없으면 None)."""
        result = await db.execute(
            select(ReservationInstance)
            .where(ReservationInstance.reservation_id == reservation_id)
            .order_by(ReservationInstance.start_at)
            .limit(1)
        )
        return result.scalar_one_or_none()

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
        """
        예약 목록 조회.

        시간 범위 필터(start_date, end_date)는 reservation_instances를 JOIN해서 처리한다.
        """
        # instances JOIN이 필요한지 판단
        need_instance_join = start_date is not None or end_date is not None

        base = select(Reservation)
        count_base = select(func.count(Reservation.id.distinct()))

        if need_instance_join:
            base = base.join(
                ReservationInstance,
                ReservationInstance.reservation_id == Reservation.id,
            )
            count_base = count_base.join(
                ReservationInstance,
                ReservationInstance.reservation_id == Reservation.id,
            )

        conditions = []
        if server_resource_id:
            conditions.append(Reservation.server_resource_id == server_resource_id)
        if user_id:
            conditions.append(Reservation.user_id == user_id)
        if status:
            conditions.append(Reservation.status == status)
        if start_date:
            conditions.append(ReservationInstance.end_at > start_date)
        if end_date:
            conditions.append(ReservationInstance.start_at < end_date)

        count_stmt = count_base.where(*conditions)
        total = (await db.execute(count_stmt)).scalar()

        stmt = (
            base.where(*conditions)
            .order_by(Reservation.created_at.desc())
            .limit(limit)
            .offset(offset)
            .distinct()
        )
        result = await db.execute(stmt)
        reservations = list(result.scalars().all())

        return reservations, total

    # ------------------------------------------------------------------ #
    # 수정 (단일 예약만; 반복 예약은 RecurringReservationService 사용)
    # ------------------------------------------------------------------ #

    @staticmethod
    async def update(
        db: AsyncSession,
        reservation_id: uuid.UUID,
        current_user: User,
        title: str | None = None,
        description: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        account_name: str | None = None,
    ) -> Reservation:
        """단일 예약 수정. 반복 예약(is_recurring=True)은 거부한다."""
        reservation = await ReservationService.get_by_id(db, reservation_id)

        if reservation.is_recurring:
            raise BadRequestError(
                "반복 예약은 이 API로 수정할 수 없습니다. "
                "개별 instance 수정은 /instances/{id} 엔드포인트를 사용하세요."
            )
        if reservation.user_id != current_user.id and current_user.role != UserRole.ADMIN:
            raise ForbiddenError("You can only modify your own reservations")
        if reservation.status == ReservationStatus.CANCELED:
            raise ConflictError("Cannot modify a canceled reservation")

        instance = await ReservationService._get_single_instance(db, reservation_id)
        if instance is None:
            raise NotFoundError("Reservation instance not found")

        if instance.end_at < datetime.now(timezone.utc):
            raise ForbiddenError("Past schedules cannot be modified.")

        now = datetime.now(timezone.utc)
        new_start = start_at or instance.start_at
        new_end = end_at or instance.end_at
        new_start_utc = new_start.astimezone(timezone.utc)

        if new_start_utc < now:
            raise BadRequestError("Reservation start time cannot be in the past")
        if new_end <= new_start:
            raise ConflictError("end_at must be after start_at")

        max_hours = get_settings().MAX_RESERVATION_HOURS
        if (new_end - new_start) > timedelta(hours=max_hours):
            raise ConflictError(
                f"Reservation duration cannot exceed {max_hours} hours"
            )

        # 메타데이터 업데이트
        if title is not None:
            reservation.title = title
        if description is not None:
            reservation.description = description
        if account_name is not None:
            reservation.account_name = account_name

        # 시간 업데이트 (instance)
        if start_at is not None:
            instance.start_at = start_at
        if end_at is not None:
            instance.end_at = end_at

        try:
            await db.commit()
            await db.refresh(reservation)
        except IntegrityError as exc:
            await db.rollback()
            _raise_conflict_from_integrity_error(exc)

        return reservation

    # ------------------------------------------------------------------ #
    # 취소
    # ------------------------------------------------------------------ #

    @staticmethod
    async def cancel(
        db: AsyncSession,
        reservation_id: uuid.UUID,
        current_user: User,
    ) -> Reservation:
        """단일 예약 취소. instance도 함께 CANCELED 처리한다."""
        reservation = await ReservationService.get_by_id(db, reservation_id)

        if reservation.user_id != current_user.id and current_user.role != UserRole.ADMIN:
            raise ForbiddenError("You can only cancel your own reservations")
        if reservation.status == ReservationStatus.CANCELED:
            raise ConflictError("Reservation is already canceled")

        instance = await ReservationService._get_single_instance(db, reservation_id)
        if instance is not None:
            if instance.end_at < datetime.now(timezone.utc):
                raise ForbiddenError("Past schedules cannot be deleted.")
            instance.status = ReservationStatus.CANCELED

        reservation.status = ReservationStatus.CANCELED
        await db.commit()
        await db.refresh(reservation)

        return reservation

    # ------------------------------------------------------------------ #
    # 가용성 확인
    # ------------------------------------------------------------------ #

    @staticmethod
    async def check_availability(
        db: AsyncSession,
        server_resource_id: uuid.UUID,
        start_at: datetime,
        end_at: datetime,
    ) -> tuple[bool, list[Reservation]]:
        """
        특정 시간대의 예약 가능 여부 확인.
        instances 테이블을 기준으로 겹치는 예약을 반환한다.
        """
        stmt = (
            select(Reservation)
            .join(
                ReservationInstance,
                ReservationInstance.reservation_id == Reservation.id,
            )
            .where(
                ReservationInstance.server_resource_id == server_resource_id,
                ReservationInstance.status == ReservationStatus.ACTIVE,
                ReservationInstance.start_at < end_at,
                ReservationInstance.end_at > start_at,
            )
            .distinct()
        )
        result = await db.execute(stmt)
        conflicts = list(result.scalars().all())

        return len(conflicts) == 0, conflicts
