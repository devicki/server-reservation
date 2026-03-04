"""반복 예약 생성 서비스

설계 원칙:
- RRULE 동적 계산 금지: Python에서 미리 날짜 목록을 계산하여 instance를 생성.
- 무한 반복 금지: end_date 없으면 생성 기준일로부터 최대 MAX_MONTHS 개월치만 생성.
- 중복 방지는 DB EXCLUDE 제약에 위임: bulk insert 후 IntegrityError 발생 시 rollback.
- 단일 예약도 동일 흐름(instance 1개)으로 처리하여 스케줄러 쿼리를 단일화.
"""
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError, ForbiddenError
from app.models.recurrence_rule import RecurrenceRule
from app.models.reservation import Reservation, ReservationStatus
from app.models.reservation_instance import ReservationInstance
from app.models.server_resource import ServerResource
from app.models.user import User, UserRole
from sqlalchemy import select

logger = logging.getLogger(__name__)

# 반복 예약 최대 생성 기간 (개월)
MAX_RECURRENCE_MONTHS = 12

# 요일 문자열 → weekday() 인덱스 매핑
_WEEKDAY_MAP = {
    "MON": 0,
    "TUE": 1,
    "WED": 2,
    "THU": 3,
    "FRI": 4,
    "SAT": 5,
    "SUN": 6,
}

FreqType = Literal["DAILY", "WEEKLY", "MONTHLY"]


@dataclass
class RecurrenceSpec:
    """반복 규칙 명세"""

    freq: FreqType
    interval: int = 1
    by_day: str | None = None        # WEEKLY: "MON,WED,FRI"
    by_month_day: int | None = None  # MONTHLY: 15


def _add_months(dt: datetime, months: int) -> datetime:
    """월 단위 덧셈 (말일 보정 포함)"""
    import calendar

    year = dt.year + (dt.month + months - 1) // 12
    month = (dt.month + months - 1) % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def compute_recurrence_dates(
    start: datetime,
    duration: timedelta,
    spec: RecurrenceSpec,
    until: datetime,
) -> list[tuple[datetime, datetime]]:
    """
    반복 규칙에 따라 (start_at, end_at) 쌍 목록을 생성.

    Args:
        start:    첫 번째 instance 시작 시각 (tzaware)
        duration: 각 instance의 지속 시간
        spec:     반복 규칙 명세
        until:    생성 상한선 (이 시각 이후 시작하는 instance는 제외)

    Returns:
        [(start_at, end_at), ...] 리스트
    """
    dates: list[tuple[datetime, datetime]] = []

    if spec.freq == "DAILY":
        cur = start
        while cur <= until:
            dates.append((cur, cur + duration))
            cur += timedelta(days=spec.interval)

    elif spec.freq == "WEEKLY":
        if not spec.by_day:
            raise BadRequestError("WEEKLY 반복에는 by_day 값이 필요합니다 (예: MON,WED)")
        target_weekdays = {
            _WEEKDAY_MAP[d.strip().upper()]
            for d in spec.by_day.split(",")
            if d.strip().upper() in _WEEKDAY_MAP
        }
        if not target_weekdays:
            raise BadRequestError(f"유효하지 않은 by_day 값: {spec.by_day}")

        # 첫 주의 시작 월요일부터 순회
        week_start = start - timedelta(days=start.weekday())
        cur_week = week_start
        while cur_week <= until:
            for wd in sorted(target_weekdays):
                candidate = cur_week + timedelta(days=wd)
                # 기준 start 시각으로 시간 부분 고정
                candidate = candidate.replace(
                    hour=start.hour,
                    minute=start.minute,
                    second=start.second,
                    microsecond=0,
                    tzinfo=start.tzinfo,
                )
                if candidate >= start and candidate <= until:
                    dates.append((candidate, candidate + duration))
            cur_week += timedelta(weeks=spec.interval)

    elif spec.freq == "MONTHLY":
        if spec.by_month_day is None:
            raise BadRequestError("MONTHLY 반복에는 by_month_day 값이 필요합니다 (예: 15)")
        cur = start
        while cur <= until:
            dates.append((cur, cur + duration))
            cur = _add_months(cur, spec.interval)

    else:
        raise BadRequestError(f"지원하지 않는 반복 주기: {spec.freq}")

    return dates


class RecurringReservationService:
    """반복 예약 생성/관리 서비스"""

    @staticmethod
    async def _get_active_resource(
        db: AsyncSession, server_resource_id: uuid.UUID
    ) -> ServerResource:
        result = await db.execute(
            select(ServerResource).where(
                ServerResource.id == server_resource_id,
                ServerResource.is_active.is_(True),
            )
        )
        resource = result.scalar_one_or_none()
        if resource is None:
            raise NotFoundError("Server resource not found or inactive")
        return resource

    # ------------------------------------------------------------------ #
    # 단일 예약 생성 (instance 기반으로 통일)
    # ------------------------------------------------------------------ #
    @staticmethod
    async def create_single(
        db: AsyncSession,
        user_id: uuid.UUID,
        server_resource_id: uuid.UUID,
        title: str,
        start_at: datetime,
        end_at: datetime,
        description: str | None = None,
        account_name: str | None = None,
    ) -> tuple[Reservation, ReservationInstance]:
        """
        단일 예약 생성.

        Reservation + ReservationInstance 1개를 함께 생성한다.
        중복 검사는 DB EXCLUDE 제약에 위임하며, IntegrityError 발생 시 ConflictError로 변환.
        """
        now = datetime.now(timezone.utc)
        start_utc = start_at.astimezone(timezone.utc)
        end_utc = end_at.astimezone(timezone.utc)

        if start_utc < now:
            raise BadRequestError("예약 시작 시각은 현재 시각 이후여야 합니다")
        if end_utc <= start_utc:
            raise BadRequestError("end_at은 start_at 이후여야 합니다")

        await RecurringReservationService._get_active_resource(db, server_resource_id)

        reservation = Reservation(
            user_id=user_id,
            server_resource_id=server_resource_id,
            title=title,
            description=description,
            account_name=account_name,
            status=ReservationStatus.ACTIVE,
        )
        db.add(reservation)
        await db.flush()  # reservation.id 확보

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
            await db.refresh(instance)
        except IntegrityError as exc:
            await db.rollback()
            _raise_conflict_from_integrity_error(exc)

        logger.info(f"단일 예약 생성 완료: reservation={reservation.id}")
        return reservation, instance

    # ------------------------------------------------------------------ #
    # 반복 예약 생성
    # ------------------------------------------------------------------ #
    @staticmethod
    async def create_recurring(
        db: AsyncSession,
        user_id: uuid.UUID,
        server_resource_id: uuid.UUID,
        title: str,
        start_at: datetime,
        end_at: datetime,
        spec: RecurrenceSpec,
        recurrence_end_date: datetime | None = None,
        description: str | None = None,
        account_name: str | None = None,
    ) -> tuple[Reservation, list[ReservationInstance]]:
        """
        반복 예약 생성.

        1. RecurrenceRule 생성
        2. Reservation 생성 (start_at/end_at = None, recurrence_rule_id 설정)
        3. 반복 날짜 계산 (Python)
        4. ReservationInstance bulk insert
        5. commit → DB EXCLUDE 제약으로 중복 자동 차단
        6. 충돌 시 rollback 후 ConflictError

        Args:
            start_at:             첫 번째 instance 시작 시각
            end_at:               첫 번째 instance 종료 시각 (duration 계산에 사용)
            spec:                 반복 규칙 명세
            recurrence_end_date:  반복 종료 상한 (None이면 start_at 기준 MAX_RECURRENCE_MONTHS개월)
        """
        now = datetime.now(timezone.utc)
        start_utc = start_at.astimezone(timezone.utc)
        end_utc = end_at.astimezone(timezone.utc)

        if start_utc < now:
            raise BadRequestError("예약 시작 시각은 현재 시각 이후여야 합니다")
        if end_utc <= start_utc:
            raise BadRequestError("end_at은 start_at 이후여야 합니다")

        await RecurringReservationService._get_active_resource(db, server_resource_id)

        duration = end_utc - start_utc

        # until 상한 결정
        until: datetime
        if recurrence_end_date is not None:
            until = recurrence_end_date.astimezone(timezone.utc)
        else:
            until = _add_months(start_utc, MAX_RECURRENCE_MONTHS)

        # 날짜 목록 계산
        date_pairs = compute_recurrence_dates(start_utc, duration, spec, until)
        if not date_pairs:
            raise BadRequestError("생성할 반복 instance가 없습니다 (날짜 범위를 확인하세요)")

        # RecurrenceRule 생성
        rule = RecurrenceRule(
            freq=spec.freq,
            interval=spec.interval,
            by_day=spec.by_day,
            by_month_day=spec.by_month_day,
            start_date=start_utc,
            end_date=until,
        )
        db.add(rule)
        await db.flush()  # rule.id 확보

        # Reservation 생성 (시간 정보는 instances에서 관리)
        reservation = Reservation(
            user_id=user_id,
            server_resource_id=server_resource_id,
            recurrence_rule_id=rule.id,
            title=title,
            description=description,
            account_name=account_name,
            status=ReservationStatus.ACTIVE,
        )
        db.add(reservation)
        await db.flush()  # reservation.id 확보

        # Instance 목록 생성
        instances = [
            ReservationInstance(
                reservation_id=reservation.id,
                server_resource_id=server_resource_id,
                start_at=s,
                end_at=e,
                status=ReservationStatus.ACTIVE,
            )
            for s, e in date_pairs
        ]
        db.add_all(instances)

        try:
            await db.commit()
            await db.refresh(reservation)
        except IntegrityError as exc:
            await db.rollback()
            _raise_conflict_from_integrity_error(exc)

        logger.info(
            f"반복 예약 생성 완료: reservation={reservation.id}, "
            f"instances={len(instances)}, rule={rule.id}"
        )
        return reservation, instances

    # ------------------------------------------------------------------ #
    # 특정 instance 수정 (이 일정만)
    # ------------------------------------------------------------------ #
    @staticmethod
    async def update_instance(
        db: AsyncSession,
        instance_id: uuid.UUID,
        current_user: User,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        title: str | None = None,
        description: str | None = None,
        account_name: str | None = None,
        status: ReservationStatus | None = None,
    ) -> ReservationInstance:
        """
        단일 instance 수정 (이 일정만).
        반복 예약의 특정 날짜만 예외 처리할 때 사용한다.
        """
        result = await db.execute(
            select(ReservationInstance).where(ReservationInstance.id == instance_id)
        )
        instance = result.scalar_one_or_none()
        if instance is None:
            raise NotFoundError("ReservationInstance not found")

        # 권한 확인: 예약 소유자 또는 admin
        rsv_result = await db.execute(
            select(Reservation).where(Reservation.id == instance.reservation_id)
        )
        reservation = rsv_result.scalar_one_or_none()
        if reservation is None:
            raise NotFoundError("Reservation not found")
        if reservation.user_id != current_user.id and current_user.role != UserRole.ADMIN:
            raise ForbiddenError("자신의 예약만 수정할 수 있습니다")

        new_start = start_at or instance.start_at
        new_end = end_at or instance.end_at
        if new_end <= new_start:
            raise BadRequestError("end_at은 start_at 이후여야 합니다")

        if start_at is not None:
            instance.start_at = start_at
        if end_at is not None:
            instance.end_at = end_at
        if status is not None:
            instance.status = status

        # 메타데이터 수정 시 부모 Reservation에 반영
        if title is not None:
            reservation.title = title
        if description is not None:
            reservation.description = description
        if account_name is not None:
            reservation.account_name = account_name

        try:
            await db.commit()
            await db.refresh(instance)
        except IntegrityError as exc:
            await db.rollback()
            _raise_conflict_from_integrity_error(exc)

        return instance

    # ------------------------------------------------------------------ #
    # 반복 예약 메타 + 이후 instance 일괄 수정
    # ------------------------------------------------------------------ #
    @staticmethod
    async def update_from(
        db: AsyncSession,
        instance_id: uuid.UUID,
        current_user: User,
        title: str | None = None,
        description: str | None = None,
        account_name: str | None = None,
        start_time_hhmm: str | None = None,  # "HH:MM"
        end_time_hhmm: str | None = None,    # "HH:MM"
    ) -> tuple[Reservation, int]:
        """
        이 일정부터 이후 모든 instance 수정.

        - 제목/설명/계정: Reservation 공통 필드 업데이트
        - 시작/종료 시각(시:분): 해당 instance 이후의 모든 ACTIVE instance 시간대 변경
          (날짜는 유지, 시각만 교체)

        Returns:
            (Reservation, 수정된 instance 수)
        """
        inst_result = await db.execute(
            select(ReservationInstance).where(ReservationInstance.id == instance_id)
        )
        instance = inst_result.scalar_one_or_none()
        if instance is None:
            raise NotFoundError("ReservationInstance not found")

        rsv_result = await db.execute(
            select(Reservation).where(Reservation.id == instance.reservation_id)
        )
        reservation = rsv_result.scalar_one_or_none()
        if reservation is None:
            raise NotFoundError("Reservation not found")
        if reservation.user_id != current_user.id and current_user.role != UserRole.ADMIN:
            raise ForbiddenError("자신의 예약만 수정할 수 있습니다")

        # 메타데이터 업데이트
        if title is not None:
            reservation.title = title
        if description is not None:
            reservation.description = description
        if account_name is not None:
            reservation.account_name = account_name

        # 이후 ACTIVE instance 목록 조회 (기준 instance 포함)
        future_result = await db.execute(
            select(ReservationInstance).where(
                ReservationInstance.reservation_id == instance.reservation_id,
                ReservationInstance.status == ReservationStatus.ACTIVE,
                ReservationInstance.start_at >= instance.start_at,
            )
        )
        future_instances = list(future_result.scalars().all())

        updated_count = 0
        if start_time_hhmm or end_time_hhmm:
            for inst in future_instances:
                # start_at 기준으로 시각 교체 (날짜는 start_at의 날짜 유지)
                if start_time_hhmm:
                    h, m = map(int, start_time_hhmm.split(":"))
                    new_start = inst.start_at.replace(hour=h, minute=m, second=0, microsecond=0)
                else:
                    new_start = inst.start_at

                # end_at은 start_at과 같은 날짜 기준으로 적용
                # (기존 예약이 자정을 넘는 경우에도 항상 start 날짜 기준으로 end 계산)
                if end_time_hhmm:
                    h, m = map(int, end_time_hhmm.split(":"))
                    new_end = new_start.replace(hour=h, minute=m, second=0, microsecond=0)
                    # end가 start보다 앞서면 다음날로 넘김 (자정 이후 종료 허용)
                    if new_end <= new_start:
                        new_end = new_end + timedelta(days=1)
                else:
                    # end_time 미지정 시 기존 duration 유지
                    original_duration = inst.end_at - inst.start_at
                    new_end = new_start + original_duration

                if new_end <= new_start:
                    raise BadRequestError("end_at은 start_at 이후여야 합니다")
                inst.start_at = new_start
                inst.end_at = new_end
                updated_count += 1

        try:
            await db.commit()
            await db.refresh(reservation)
        except IntegrityError as exc:
            await db.rollback()
            _raise_conflict_from_integrity_error(exc)

        return reservation, updated_count

    # ------------------------------------------------------------------ #
    # 반복 예약 취소 (instance 기반)
    # ------------------------------------------------------------------ #

    @staticmethod
    async def _get_instance_with_reservation(
        db: AsyncSession,
        instance_id: uuid.UUID,
        current_user: User,
    ) -> tuple[ReservationInstance, Reservation]:
        """instance와 부모 reservation을 조회하고 권한을 검사한다."""
        inst_result = await db.execute(
            select(ReservationInstance).where(ReservationInstance.id == instance_id)
        )
        instance = inst_result.scalar_one_or_none()
        if instance is None:
            raise NotFoundError("ReservationInstance not found")

        rsv_result = await db.execute(
            select(Reservation).where(Reservation.id == instance.reservation_id)
        )
        reservation = rsv_result.scalar_one_or_none()
        if reservation is None:
            raise NotFoundError("Reservation not found")
        if reservation.user_id != current_user.id and current_user.role != UserRole.ADMIN:
            raise ForbiddenError("자신의 예약만 취소할 수 있습니다")

        return instance, reservation

    @staticmethod
    async def _cancel_reservation_if_all_done(
        db: AsyncSession, reservation: Reservation
    ) -> None:
        """모든 instance가 ACTIVE가 아니면 reservation도 CANCELED로 전환."""
        remaining = await db.execute(
            select(ReservationInstance).where(
                ReservationInstance.reservation_id == reservation.id,
                ReservationInstance.status == ReservationStatus.ACTIVE,
            )
        )
        if not remaining.scalars().first():
            reservation.status = ReservationStatus.CANCELED

    @staticmethod
    async def cancel_instance(
        db: AsyncSession,
        instance_id: uuid.UUID,
        current_user: User,
    ) -> tuple[ReservationInstance, Reservation]:
        """
        이 일정만 취소.

        - 해당 instance를 CANCELED 처리.
        - 남은 ACTIVE instance가 없으면 부모 reservation도 CANCELED 처리.

        Returns:
            (취소된 instance, 부모 reservation)
        """
        instance, reservation = await RecurringReservationService._get_instance_with_reservation(
            db, instance_id, current_user
        )

        if instance.status == ReservationStatus.CANCELED:
            raise ConflictError("이미 취소된 일정입니다")
        if instance.end_at < datetime.now(timezone.utc):
            raise ForbiddenError("과거 일정은 취소할 수 없습니다")

        instance.status = ReservationStatus.CANCELED
        await RecurringReservationService._cancel_reservation_if_all_done(db, reservation)

        await db.commit()
        await db.refresh(instance)
        await db.refresh(reservation)

        logger.info(
            f"반복 예약 단건 취소: instance={instance_id}, reservation={reservation.id}"
        )
        return instance, reservation

    @staticmethod
    async def cancel_from(
        db: AsyncSession,
        instance_id: uuid.UUID,
        current_user: User,
    ) -> tuple[Reservation, int]:
        """
        이 일정부터 이후 모든 instance 취소.

        - 기준 instance의 start_at 이후(기준 포함) ACTIVE instance를 모두 CANCELED 처리.
        - 남은 ACTIVE instance가 없으면 부모 reservation도 CANCELED 처리.

        Returns:
            (부모 reservation, 취소된 instance 수)
        """
        instance, reservation = await RecurringReservationService._get_instance_with_reservation(
            db, instance_id, current_user
        )

        future_result = await db.execute(
            select(ReservationInstance).where(
                ReservationInstance.reservation_id == instance.reservation_id,
                ReservationInstance.status == ReservationStatus.ACTIVE,
                ReservationInstance.start_at >= instance.start_at,
            )
        )
        future_instances = list(future_result.scalars().all())

        for inst in future_instances:
            inst.status = ReservationStatus.CANCELED

        await RecurringReservationService._cancel_reservation_if_all_done(db, reservation)

        await db.commit()
        await db.refresh(reservation)

        logger.info(
            f"반복 예약 이후 전체 취소: from_instance={instance_id}, "
            f"reservation={reservation.id}, 취소된 instances={len(future_instances)}"
        )
        return reservation, len(future_instances)

    # ------------------------------------------------------------------ #
    # 반복 예약 전체 취소 (reservation_id 기반, 하위 호환)
    # ------------------------------------------------------------------ #
    @staticmethod
    async def cancel_recurring(
        db: AsyncSession,
        reservation_id: uuid.UUID,
        current_user: User,
        cancel_from: datetime | None = None,
    ) -> int:
        """
        반복 예약 취소.

        Args:
            cancel_from: 이 시각 이후의 instance만 취소 (None이면 전체 취소)

        Returns:
            취소된 instance 수
        """
        rsv_result = await db.execute(
            select(Reservation).where(Reservation.id == reservation_id)
        )
        reservation = rsv_result.scalar_one_or_none()
        if reservation is None:
            raise NotFoundError("Reservation not found")
        if reservation.user_id != current_user.id and current_user.role != UserRole.ADMIN:
            raise ForbiddenError("자신의 예약만 취소할 수 있습니다")

        instance_query = select(ReservationInstance).where(
            ReservationInstance.reservation_id == reservation_id,
            ReservationInstance.status == ReservationStatus.ACTIVE,
        )
        if cancel_from is not None:
            instance_query = instance_query.where(
                ReservationInstance.start_at >= cancel_from
            )

        result = await db.execute(instance_query)
        instances = result.scalars().all()

        for inst in instances:
            inst.status = ReservationStatus.CANCELED

        # 모든 instance가 취소되면 reservation도 취소
        all_result = await db.execute(
            select(ReservationInstance).where(
                ReservationInstance.reservation_id == reservation_id,
                ReservationInstance.status == ReservationStatus.ACTIVE,
            )
        )
        remaining = all_result.scalars().all()
        if not remaining:
            reservation.status = ReservationStatus.CANCELED

        await db.commit()
        logger.info(
            f"반복 예약 취소: reservation={reservation_id}, 취소된 instances={len(instances)}"
        )
        return len(instances)


# ------------------------------------------------------------------ #
# 내부 헬퍼
# ------------------------------------------------------------------ #

def _raise_conflict_from_integrity_error(exc: IntegrityError) -> None:
    """
    IntegrityError를 분석하여 적절한 ConflictError를 발생시킨다.
    no_overlap_per_server EXCLUDE 제약 위반 여부를 판단한다.
    """
    error_str = str(exc.orig).lower() if exc.orig else str(exc).lower()
    if "no_overlap_per_server" in error_str or "exclusion constraint" in error_str:
        raise ConflictError(
            "해당 서버에 시간이 겹치는 예약이 이미 존재합니다 "
            "(DB EXCLUDE 제약 위반)"
        )
    # 그 외 integrity 오류 (예: FK 위반 등)
    logger.error(f"Unexpected IntegrityError: {exc}", exc_info=True)
    raise ConflictError("예약 저장 중 데이터 무결성 오류가 발생했습니다")
