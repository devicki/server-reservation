"""Session Scheduler - 예약 시작/종료 시점에 자동으로 세션 활성화/비활성화

스케줄러는 reservation_instances 테이블만 조회한다.
- 단일 예약과 반복 예약 모두 instance로 통일되어 있으므로 로직이 동일하다.
- RRULE 계산 등 동적 처리는 일절 수행하지 않는다.

핵심 쿼리 (1분마다 실행):
    SELECT r.account_name
    FROM reservation_instances ri
    JOIN reservations r ON r.id = ri.reservation_id
    WHERE ri.server_resource_id = :server_id
      AND ri.status = 'active'
      AND NOW() BETWEEN ri.start_at AND ri.end_at;
"""
import logging
import uuid
from datetime import datetime, timezone

from app.config import get_settings
from app.database import async_session_factory
from app.models.reservation import Reservation, ReservationStatus
from app.models.reservation_instance import ReservationInstance
from app.models.reservation_session_log import ReservationSessionLog, SessionEventType
from app.services.session_manager import SessionManager
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class SessionScheduler:
    """예약 기반 세션 스케줄링 서비스 (instance 기반)"""

    @staticmethod
    def get_exception_accounts(reservation: Reservation) -> set[str]:
        """
        예약에 대한 모든 예외 계정 목록 반환

        예외 계정:
        1. 시스템 기본 예외 (EXCLUDE_USERS)
        2. 서버별 추가 예외 (ServerResource.account_exclusions)
        3. 현재 예약자 (Reservation.account_name)
        """
        settings = get_settings()
        exceptions = set(settings.EXCLUDE_USERS)

        if reservation.server_resource.account_exclusions:
            server_exceptions = [
                x.strip()
                for x in reservation.server_resource.account_exclusions.split(",")
                if x.strip()
            ]
            exceptions.update(server_exceptions)

        if reservation.account_name:
            exceptions.add(reservation.account_name)

        return exceptions

    # ------------------------------------------------------------------ #
    # 이벤트 로그 조회 (instance_id 기준)
    # ------------------------------------------------------------------ #

    @staticmethod
    async def get_event_logged_instance_ids(
        db: AsyncSession,
        instance_ids: list[uuid.UUID],
        event_type: SessionEventType,
    ) -> set[uuid.UUID]:
        """여러 instance에 대해 이미 로깅된 이벤트가 있는 ID 집합 반환 (배치 조회)."""
        if not instance_ids:
            return set()
        stmt = select(ReservationSessionLog.reservation_instance_id).where(
            ReservationSessionLog.reservation_instance_id.in_(instance_ids),
            ReservationSessionLog.event_type == event_type,
        )
        result = await db.execute(stmt)
        return {row[0] for row in result.all()}

    @staticmethod
    async def log_event(
        db: AsyncSession,
        instance_id: uuid.UUID,
        event_type: SessionEventType,
        details: dict | None = None,
    ) -> None:
        """세션 이벤트 로그 기록 (instance 기준)."""
        log = ReservationSessionLog(
            reservation_instance_id=instance_id,
            event_type=event_type,
            details=details,
        )
        db.add(log)
        await db.commit()

    # ------------------------------------------------------------------ #
    # 활성화 / 비활성화
    # ------------------------------------------------------------------ #

    @staticmethod
    async def activate_reservation(
        db: AsyncSession, instance: ReservationInstance
    ) -> dict:
        """
        예약 활성화 - instance 시작 시 실행

        1. 예약자 계정 잠금 해제
        2. 예외 계정 제외 모든 계정 잠금
        3. 예외 계정 제외 모든 프로세스 종료
        """
        reservation = instance.reservation
        logger.info(
            f"Activating instance {instance.id} (reservation={reservation.id}) "
            f"for '{reservation.account_name}' on '{reservation.server_resource.name}'"
        )

        server = reservation.server_resource
        result = {
            "instance_id": str(instance.id),
            "reservation_id": str(reservation.id),
            "account_name": reservation.account_name,
            "server_name": server.name,
            "steps": [],
        }

        exception_accounts = SessionScheduler.get_exception_accounts(reservation)
        logger.info(f"Exception accounts: {exception_accounts}")
        result["exception_accounts"] = list(exception_accounts)

        if reservation.account_name:
            unlock_result = SessionManager.unlock_user(server, reservation.account_name)
            result["steps"].append({
                "step": "unlock_reservee",
                "ok": unlock_result.ok,
                "message": unlock_result.message,
                "details": unlock_result.details,
            })
            if not unlock_result.ok:
                logger.error(f"Failed to unlock reservee account: {unlock_result.message}")
        else:
            logger.warning(f"Instance {instance.id} has no account_name, skipping unlock")
            result["steps"].append({
                "step": "unlock_reservee",
                "ok": False,
                "message": "No account_name specified in reservation",
            })

        lock_result = SessionManager.lock_all_except(server, exception_accounts)
        result["steps"].append({
            "step": "lock_others",
            "ok": lock_result.ok,
            "message": lock_result.message,
            "details": lock_result.details,
        })
        if not lock_result.ok:
            logger.warning(f"Some accounts failed to lock: {lock_result.details}")

        kill_result = SessionManager.kill_processes_except(server, exception_accounts)
        result["steps"].append({
            "step": "kill_processes",
            "ok": kill_result.ok,
            "message": kill_result.message,
            "details": kill_result.details,
        })
        if not kill_result.ok:
            logger.warning(f"Some processes failed to kill: {kill_result.details}")

        all_ok = all(step["ok"] for step in result["steps"] if step.get("ok") is not None)
        result["success"] = all_ok

        logger.info(
            f"Instance {instance.id} activation {'succeeded' if all_ok else 'completed with errors'}"
        )
        return result

    @staticmethod
    async def deactivate_reservation(
        db: AsyncSession, instance: ReservationInstance
    ) -> dict:
        """
        예약 비활성화 - instance 종료 시 실행

        1. 예약자 프로세스 강제 종료 (SIGKILL)
        2. 예약자 계정 잠금
        """
        reservation = instance.reservation
        logger.info(
            f"Deactivating instance {instance.id} (reservation={reservation.id}) "
            f"for '{reservation.account_name}' on '{reservation.server_resource.name}'"
        )

        server = reservation.server_resource
        result = {
            "instance_id": str(instance.id),
            "reservation_id": str(reservation.id),
            "account_name": reservation.account_name,
            "server_name": server.name,
            "steps": [],
        }

        if not reservation.account_name:
            logger.warning(
                f"Instance {instance.id} has no account_name, skipping deactivation"
            )
            result["steps"].append({
                "step": "deactivate",
                "ok": False,
                "message": "No account_name specified in reservation",
            })
            result["success"] = False
            return result

        kill_result = SessionManager.kill_user_processes(
            server, reservation.account_name, force=True
        )
        result["steps"].append({
            "step": "kill_processes",
            "ok": kill_result.ok,
            "message": kill_result.message,
            "details": kill_result.details,
        })
        if not kill_result.ok:
            logger.warning(
                f"Failed to kill processes for '{reservation.account_name}': {kill_result.message}"
            )

        lock_result = SessionManager.lock_user(server, reservation.account_name)
        result["steps"].append({
            "step": "lock_user",
            "ok": lock_result.ok,
            "message": lock_result.message,
            "details": lock_result.details,
        })
        if not lock_result.ok:
            logger.error(
                f"Failed to lock user '{reservation.account_name}': {lock_result.message}"
            )

        all_ok = all(step["ok"] for step in result["steps"])
        result["success"] = all_ok

        logger.info(
            f"Instance {instance.id} deactivation {'succeeded' if all_ok else 'completed with errors'}"
        )
        return result

    # ------------------------------------------------------------------ #
    # 스케줄러 메인 루프
    # ------------------------------------------------------------------ #

    @staticmethod
    async def process_reservation_events() -> dict:
        """
        스케줄러 메인 로직 - 매 1분마다 실행

        reservation_instances 테이블만 조회한다 (RRULE 계산 없음).

        1. start_at <= now < end_at 이고 아직 활성화 안 된 instance → 활성화
        2. end_at <= now 이고 아직 비활성화 안 된 instance → 비활성화
        """
        logger.info("Processing reservation events (instance-based)...")

        async with async_session_factory() as db:
            now = datetime.now(timezone.utc)
            summary = {
                "timestamp": now.isoformat(),
                "activated": [],
                "deactivated": [],
                "errors": [],
            }

            try:
                # ------------------------------------------------------ #
                # 1. 시작할 instance 찾기
                # ------------------------------------------------------ #
                starting_stmt = (
                    select(ReservationInstance)
                    .where(
                        ReservationInstance.start_at <= now,
                        ReservationInstance.end_at > now,
                        ReservationInstance.status == ReservationStatus.ACTIVE,
                    )
                    .order_by(ReservationInstance.start_at)
                )
                result = await db.execute(starting_stmt)
                starting_instances = result.scalars().all()
                starting_ids = [i.id for i in starting_instances]
                already_activated = await SessionScheduler.get_event_logged_instance_ids(
                    db, starting_ids, SessionEventType.ACTIVATED
                )

                for instance in starting_instances:
                    if instance.id in already_activated:
                        logger.debug(f"Instance {instance.id} already activated, skipping")
                        continue

                    try:
                        activation_result = await SessionScheduler.activate_reservation(
                            db, instance
                        )
                        await SessionScheduler.log_event(
                            db,
                            instance.id,
                            SessionEventType.ACTIVATED
                            if activation_result["success"]
                            else SessionEventType.ERROR,
                            activation_result,
                        )
                        summary["activated"].append({
                            "instance_id": str(instance.id),
                            "reservation_id": str(instance.reservation_id),
                            "success": activation_result["success"],
                        })
                    except Exception as e:
                        logger.error(
                            f"Error activating instance {instance.id}: {e}", exc_info=True
                        )
                        summary["errors"].append({
                            "instance_id": str(instance.id),
                            "operation": "activate",
                            "error": str(e),
                        })
                        await SessionScheduler.log_event(
                            db,
                            instance.id,
                            SessionEventType.ERROR,
                            {"error": str(e), "operation": "activate"},
                        )

                # ------------------------------------------------------ #
                # 2. 종료할 instance 찾기
                # ------------------------------------------------------ #
                ending_stmt = (
                    select(ReservationInstance)
                    .where(
                        ReservationInstance.end_at <= now,
                        ReservationInstance.status == ReservationStatus.ACTIVE,
                    )
                    .order_by(ReservationInstance.end_at)
                )
                result = await db.execute(ending_stmt)
                ending_instances = result.scalars().all()
                ending_ids = [i.id for i in ending_instances]
                already_deactivated = await SessionScheduler.get_event_logged_instance_ids(
                    db, ending_ids, SessionEventType.DEACTIVATED
                )

                for instance in ending_instances:
                    if instance.id in already_deactivated:
                        logger.debug(f"Instance {instance.id} already deactivated, skipping")
                        continue

                    try:
                        deactivation_result = await SessionScheduler.deactivate_reservation(
                            db, instance
                        )

                        if deactivation_result["success"]:
                            instance.status = ReservationStatus.COMPLETED

                        await SessionScheduler.log_event(
                            db,
                            instance.id,
                            SessionEventType.DEACTIVATED
                            if deactivation_result["success"]
                            else SessionEventType.ERROR,
                            deactivation_result,
                        )
                        summary["deactivated"].append({
                            "instance_id": str(instance.id),
                            "reservation_id": str(instance.reservation_id),
                            "success": deactivation_result["success"],
                        })
                    except Exception as e:
                        logger.error(
                            f"Error deactivating instance {instance.id}: {e}", exc_info=True
                        )
                        summary["errors"].append({
                            "instance_id": str(instance.id),
                            "operation": "deactivate",
                            "error": str(e),
                        })
                        await SessionScheduler.log_event(
                            db,
                            instance.id,
                            SessionEventType.ERROR,
                            {"error": str(e), "operation": "deactivate"},
                        )

                logger.info(
                    f"Event processing completed: "
                    f"{len(summary['activated'])} activated, "
                    f"{len(summary['deactivated'])} deactivated, "
                    f"{len(summary['errors'])} errors"
                )

            except Exception as e:
                logger.error(
                    f"Fatal error in process_reservation_events: {e}", exc_info=True
                )
                summary["errors"].append({"operation": "scheduler", "error": str(e)})

            return summary

    # ------------------------------------------------------------------ #
    # 특정 서버의 현재 유효한 예약 account_name 조회 (헬퍼)
    # ------------------------------------------------------------------ #

    @staticmethod
    async def get_active_account_for_server(
        db: AsyncSession, server_resource_id: uuid.UUID
    ) -> str | None:
        """
        특정 서버에서 지금 이 순간 유효한 예약의 account_name을 반환.

        SQL 등가:
            SELECT r.account_name
            FROM reservation_instances ri
            JOIN reservations r ON r.id = ri.reservation_id
            WHERE ri.server_resource_id = :server_id
              AND ri.status = 'active'
              AND NOW() BETWEEN ri.start_at AND ri.end_at
            LIMIT 1;
        """
        now = datetime.now(timezone.utc)
        stmt = (
            select(Reservation.account_name)
            .join(ReservationInstance, ReservationInstance.reservation_id == Reservation.id)
            .where(
                ReservationInstance.server_resource_id == server_resource_id,
                ReservationInstance.status == ReservationStatus.ACTIVE,
                ReservationInstance.start_at <= now,
                ReservationInstance.end_at > now,
            )
            .limit(1)
        )
        result = await db.execute(stmt)
        row = result.scalar_one_or_none()
        return row
