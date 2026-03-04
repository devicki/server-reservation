"""
반복 예약 서비스 단위 테스트

테스트 범위:
- compute_recurrence_dates: DAILY / WEEKLY / MONTHLY 날짜 계산
- overlap 검출: 동일 서버에 겹치는 instance가 있을 때 ConflictError
- 단일/반복 예약 생성 성공 경로 (DB 없이 mock 사용)
- _raise_conflict_from_integrity_error 헬퍼

DB 레벨 EXCLUDE 제약 통합 테스트는 별도 integration 테스트에서 수행.
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.recurring_reservation import (
    FreqType,
    RecurrenceSpec,
    RecurringReservationService,
    _raise_conflict_from_integrity_error,
    compute_recurrence_dates,
)
from app.core.exceptions import BadRequestError, ConflictError


# ------------------------------------------------------------------ #
# 헬퍼
# ------------------------------------------------------------------ #

def dt(offset_days: float = 0, hour: int = 10, minute: int = 0) -> datetime:
    """오늘 기준 UTC datetime 생성 헬퍼"""
    base = datetime.now(timezone.utc).replace(
        hour=hour, minute=minute, second=0, microsecond=0
    )
    return base + timedelta(days=offset_days)


# ------------------------------------------------------------------ #
# compute_recurrence_dates - DAILY
# ------------------------------------------------------------------ #

class TestComputeRecurrenceDatesDaily:
    def test_daily_generates_correct_count(self):
        start = dt(1)
        until = start + timedelta(days=6)
        duration = timedelta(hours=2)
        spec = RecurrenceSpec(freq="DAILY", interval=1)

        pairs = compute_recurrence_dates(start, duration, spec, until)

        assert len(pairs) == 7
        for s, e in pairs:
            assert (e - s) == duration

    def test_daily_interval_2(self):
        start = dt(1)
        until = start + timedelta(days=8)
        spec = RecurrenceSpec(freq="DAILY", interval=2)

        pairs = compute_recurrence_dates(start, timedelta(hours=1), spec, until)

        assert len(pairs) == 5  # day 0, 2, 4, 6, 8

    def test_daily_start_equals_until_includes_start(self):
        start = dt(1)
        spec = RecurrenceSpec(freq="DAILY", interval=1)

        pairs = compute_recurrence_dates(start, timedelta(hours=1), spec, start)

        assert len(pairs) == 1

    def test_daily_until_before_start_returns_empty(self):
        start = dt(5)
        until = dt(3)
        spec = RecurrenceSpec(freq="DAILY", interval=1)

        pairs = compute_recurrence_dates(start, timedelta(hours=1), spec, until)

        assert pairs == []


# ------------------------------------------------------------------ #
# compute_recurrence_dates - WEEKLY
# ------------------------------------------------------------------ #

class TestComputeRecurrenceDatesWeekly:
    def test_weekly_mon_wed_fri_two_weeks(self):
        # 다음 주 월요일 시작
        today = datetime.now(timezone.utc)
        days_until_monday = (7 - today.weekday()) % 7 or 7
        monday = (today + timedelta(days=days_until_monday)).replace(
            hour=10, minute=0, second=0, microsecond=0
        )
        until = monday + timedelta(weeks=2)
        spec = RecurrenceSpec(freq="WEEKLY", interval=1, by_day="MON,WED,FRI")

        pairs = compute_recurrence_dates(monday, timedelta(hours=2), spec, until)

        # 2주 × 3일 = 6개 (단, until이 포함 여부에 따라 ±1)
        assert len(pairs) >= 5
        # 모든 시작 시각이 MON/WED/FRI인지 확인
        for s, _ in pairs:
            assert s.weekday() in (0, 2, 4), f"{s} is not MON/WED/FRI"

    def test_weekly_missing_by_day_raises(self):
        spec = RecurrenceSpec(freq="WEEKLY", interval=1, by_day=None)
        with pytest.raises(BadRequestError, match="by_day"):
            compute_recurrence_dates(dt(1), timedelta(hours=1), spec, dt(10))

    def test_weekly_invalid_by_day_raises(self):
        spec = RecurrenceSpec(freq="WEEKLY", interval=1, by_day="INVALID")
        with pytest.raises(BadRequestError, match="by_day"):
            compute_recurrence_dates(dt(1), timedelta(hours=1), spec, dt(10))

    def test_weekly_interval_2(self):
        today = datetime.now(timezone.utc)
        days_until_monday = (7 - today.weekday()) % 7 or 7
        monday = (today + timedelta(days=days_until_monday)).replace(
            hour=9, minute=0, second=0, microsecond=0
        )
        until = monday + timedelta(weeks=4)
        spec = RecurrenceSpec(freq="WEEKLY", interval=2, by_day="MON")

        pairs = compute_recurrence_dates(monday, timedelta(hours=1), spec, until)

        # 격주 월요일: 0주, 2주, 4주 → 3개
        assert len(pairs) == 3


# ------------------------------------------------------------------ #
# compute_recurrence_dates - MONTHLY
# ------------------------------------------------------------------ #

class TestComputeRecurrenceDatesMonthly:
    def test_monthly_3_months(self):
        start = dt(1).replace(day=15, hour=10, minute=0, second=0, microsecond=0)
        until = start + timedelta(days=90)
        spec = RecurrenceSpec(freq="MONTHLY", interval=1, by_month_day=15)

        pairs = compute_recurrence_dates(start, timedelta(hours=2), spec, until)

        assert len(pairs) == 3

    def test_monthly_missing_by_month_day_raises(self):
        spec = RecurrenceSpec(freq="MONTHLY", interval=1, by_month_day=None)
        with pytest.raises(BadRequestError, match="by_month_day"):
            compute_recurrence_dates(dt(1), timedelta(hours=1), spec, dt(60))

    def test_monthly_interval_2(self):
        start = dt(1).replace(day=1, hour=10, minute=0, second=0, microsecond=0)
        until = start + timedelta(days=180)
        spec = RecurrenceSpec(freq="MONTHLY", interval=2, by_month_day=1)

        pairs = compute_recurrence_dates(start, timedelta(hours=1), spec, until)

        # 격월: 0, 2, 4개월 → 최대 3~4개
        assert len(pairs) >= 3


# ------------------------------------------------------------------ #
# compute_recurrence_dates - 미지원 freq
# ------------------------------------------------------------------ #

class TestComputeRecurrenceDatesUnknown:
    def test_unknown_freq_raises(self):
        spec = RecurrenceSpec(freq="HOURLY")  # type: ignore[arg-type]
        with pytest.raises(BadRequestError, match="지원하지 않는"):
            compute_recurrence_dates(dt(1), timedelta(hours=1), spec, dt(10))


# ------------------------------------------------------------------ #
# overlap 검출 로직 (단위 테스트)
# ------------------------------------------------------------------ #

class TestOverlapDetection:
    """
    DB EXCLUDE 제약은 통합 테스트에서 검증.
    여기서는 Python 레벨의 overlap 계산 로직을 테스트한다.
    """

    @staticmethod
    def overlaps(a_start, a_end, b_start, b_end) -> bool:
        """두 구간이 겹치는지 확인 (반열린 구간 [s, e))"""
        return a_start < b_end and a_end > b_start

    def test_no_overlap(self):
        s1, e1 = dt(1, 10), dt(1, 12)
        s2, e2 = dt(1, 13), dt(1, 15)
        assert not self.overlaps(s1, e1, s2, e2)

    def test_adjacent_no_overlap(self):
        """경계가 맞닿는 경우 겹치지 않음"""
        s1, e1 = dt(1, 10), dt(1, 12)
        s2, e2 = dt(1, 12), dt(1, 14)
        assert not self.overlaps(s1, e1, s2, e2)

    def test_partial_overlap(self):
        s1, e1 = dt(1, 10), dt(1, 13)
        s2, e2 = dt(1, 12), dt(1, 15)
        assert self.overlaps(s1, e1, s2, e2)

    def test_contained_overlap(self):
        s1, e1 = dt(1, 9), dt(1, 17)
        s2, e2 = dt(1, 10), dt(1, 12)
        assert self.overlaps(s1, e1, s2, e2)

    def test_identical_overlap(self):
        s, e = dt(1, 10), dt(1, 12)
        assert self.overlaps(s, e, s, e)

    def test_recurrence_dates_no_internal_overlap(self):
        """DAILY 반복 날짜끼리는 서로 겹치지 않아야 한다"""
        start = dt(1, 9)
        duration = timedelta(hours=2)
        spec = RecurrenceSpec(freq="DAILY", interval=1)
        until = start + timedelta(days=6)

        pairs = compute_recurrence_dates(start, duration, spec, until)

        for i in range(len(pairs)):
            for j in range(i + 1, len(pairs)):
                s1, e1 = pairs[i]
                s2, e2 = pairs[j]
                assert not self.overlaps(s1, e1, s2, e2), (
                    f"Internal overlap detected: {s1}-{e1} vs {s2}-{e2}"
                )


# ------------------------------------------------------------------ #
# _raise_conflict_from_integrity_error
# ------------------------------------------------------------------ #

class TestRaiseConflictFromIntegrityError:
    def test_no_overlap_constraint_raises_conflict(self):
        mock_exc = MagicMock()
        mock_exc.orig = Exception("no_overlap_per_server exclusion constraint violated")

        with pytest.raises(ConflictError, match="EXCLUDE"):
            _raise_conflict_from_integrity_error(mock_exc)

    def test_exclusion_constraint_keyword(self):
        mock_exc = MagicMock()
        mock_exc.orig = Exception("exclusion constraint 'no_overlap_per_server' violated")

        with pytest.raises(ConflictError):
            _raise_conflict_from_integrity_error(mock_exc)

    def test_other_integrity_error_raises_generic_conflict(self):
        mock_exc = MagicMock()
        mock_exc.orig = Exception("foreign key constraint violated")

        with pytest.raises(ConflictError, match="무결성"):
            _raise_conflict_from_integrity_error(mock_exc)


# ------------------------------------------------------------------ #
# RecurringReservationService.create_single (mock DB)
# ------------------------------------------------------------------ #

class TestCreateSingle:
    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    @pytest.fixture
    def mock_resource(self):
        resource = MagicMock()
        resource.id = uuid.uuid4()
        resource.is_active = True
        return resource

    @pytest.mark.asyncio
    async def test_start_in_past_raises(self, mock_db):
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        end = datetime.now(timezone.utc) + timedelta(hours=1)
        with pytest.raises(BadRequestError, match="현재 시각 이후"):
            await RecurringReservationService.create_single(
                mock_db, uuid.uuid4(), uuid.uuid4(), "test", past, end
            )

    @pytest.mark.asyncio
    async def test_end_before_start_raises(self, mock_db):
        start = datetime.now(timezone.utc) + timedelta(hours=1)
        end = start - timedelta(minutes=30)
        with pytest.raises(BadRequestError, match="end_at"):
            await RecurringReservationService.create_single(
                mock_db, uuid.uuid4(), uuid.uuid4(), "test", start, end
            )

    @pytest.mark.asyncio
    async def test_resource_not_found_raises(self, mock_db):
        mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
        start = datetime.now(timezone.utc) + timedelta(hours=1)
        end = start + timedelta(hours=2)
        from app.core.exceptions import NotFoundError
        with pytest.raises(NotFoundError):
            await RecurringReservationService.create_single(
                mock_db, uuid.uuid4(), uuid.uuid4(), "test", start, end
            )


# ------------------------------------------------------------------ #
# RecurringReservationService.create_recurring (mock DB)
# ------------------------------------------------------------------ #

class TestCreateRecurring:
    @pytest.mark.asyncio
    async def test_empty_date_range_raises(self):
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=MagicMock(is_active=True))
        db.execute = AsyncMock(return_value=mock_result)
        db.flush = AsyncMock()

        start = datetime.now(timezone.utc) + timedelta(hours=1)
        end = start + timedelta(hours=2)
        # until이 start보다 이전이면 빈 리스트 → BadRequestError
        spec = RecurrenceSpec(freq="DAILY", interval=1)
        past_until = start - timedelta(days=1)

        with pytest.raises(BadRequestError, match="instance가 없습니다"):
            await RecurringReservationService.create_recurring(
                db,
                uuid.uuid4(),
                uuid.uuid4(),
                "test",
                start,
                end,
                spec,
                recurrence_end_date=past_until,
            )

    @pytest.mark.asyncio
    async def test_integrity_error_triggers_rollback(self):
        from sqlalchemy.exc import IntegrityError

        db = AsyncMock()
        mock_resource = MagicMock()
        mock_resource.is_active = True
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_resource)
        db.execute = AsyncMock(return_value=mock_result)
        db.flush = AsyncMock()
        db.rollback = AsyncMock()

        # commit 시 IntegrityError (no_overlap_per_server 위반) 시뮬레이션
        orig_exc = Exception("no_overlap_per_server exclusion constraint violated")
        db.commit = AsyncMock(
            side_effect=IntegrityError("overlap", {}, orig_exc)
        )

        start = datetime.now(timezone.utc) + timedelta(hours=1)
        end = start + timedelta(hours=2)
        spec = RecurrenceSpec(freq="DAILY", interval=1)
        until = start + timedelta(days=3)

        with pytest.raises(ConflictError, match="EXCLUDE"):
            await RecurringReservationService.create_recurring(
                db,
                uuid.uuid4(),
                uuid.uuid4(),
                "test",
                start,
                end,
                spec,
                recurrence_end_date=until,
            )

        db.rollback.assert_called_once()
