"""Session Scheduler - 예약 시작/종료 시점에 자동으로 세션 활성화/비활성화"""
import logging
from datetime import datetime, timezone

from app.config import get_settings
from app.database import async_session_factory
from app.models.reservation import Reservation, ReservationStatus
from app.models.reservation_session_log import ReservationSessionLog, SessionEventType
from app.services.session_manager import SessionManager
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class SessionScheduler:
    """예약 기반 세션 스케줄링 서비스"""

    @staticmethod
    def get_exception_accounts(reservation: Reservation) -> set[str]:
        """
        예약에 대한 모든 예외 계정 목록 반환
        
        예외 계정:
        1. 시스템 기본 예외 (EXCLUDE_USERS)
        2. 서버별 추가 예외 (ServerResource.account_exclusions)
        3. 현재 예약자 (Reservation.account_name)
        
        Args:
            reservation: 예약 객체
            
        Returns:
            예외 계정 집합
        """
        settings = get_settings()
        exceptions = set(settings.EXCLUDE_USERS)

        # 서버별 예외 추가
        if reservation.server_resource.account_exclusions:
            server_exceptions = [
                x.strip()
                for x in reservation.server_resource.account_exclusions.split(',')
                if x.strip()
            ]
            exceptions.update(server_exceptions)

        # 현재 예약자 추가 (예약자는 항상 예외)
        if reservation.account_name:
            exceptions.add(reservation.account_name)

        return exceptions

    @staticmethod
    async def has_event_logged(
        db: AsyncSession,
        reservation_id: str,
        event_type: SessionEventType
    ) -> bool:
        """
        특정 예약에 대해 이벤트가 이미 로깅되었는지 확인 (중복 실행 방지)
        
        Args:
            db: 데이터베이스 세션
            reservation_id: 예약 ID
            event_type: 이벤트 타입
            
        Returns:
            이미 로깅되었으면 True
        """
        stmt = select(ReservationSessionLog).where(
            and_(
                ReservationSessionLog.reservation_id == reservation_id,
                ReservationSessionLog.event_type == event_type
            )
        )
        result = await db.execute(stmt)
        log = result.scalar_one_or_none()
        return log is not None

    @staticmethod
    async def log_event(
        db: AsyncSession,
        reservation_id: str,
        event_type: SessionEventType,
        details: dict | None = None
    ) -> None:
        """
        세션 이벤트 로그 기록
        
        Args:
            db: 데이터베이스 세션
            reservation_id: 예약 ID
            event_type: 이벤트 타입
            details: 상세 정보 (JSON)
        """
        log = ReservationSessionLog(
            reservation_id=reservation_id,
            event_type=event_type,
            details=details
        )
        db.add(log)
        await db.commit()

    @staticmethod
    async def activate_reservation(db: AsyncSession, reservation: Reservation) -> dict:
        """
        예약 활성화 - 예약 시작 시 실행
        
        1. 예약자 계정 잠금 해제
        2. 예외 계정 제외 모든 계정 잠금
        3. 예외 계정 제외 모든 프로세스 종료
        
        Args:
            db: 데이터베이스 세션
            reservation: 예약 객체
            
        Returns:
            실행 결과 딕셔너리
        """
        logger.info(f"Activating reservation {reservation.id} for '{reservation.account_name}' on '{reservation.server_resource.name}'")

        server = reservation.server_resource
        result = {
            "reservation_id": str(reservation.id),
            "account_name": reservation.account_name,
            "server_name": server.name,
            "steps": []
        }

        # 예외 계정 목록 생성
        exception_accounts = SessionScheduler.get_exception_accounts(reservation)
        logger.info(f"Exception accounts: {exception_accounts}")
        result["exception_accounts"] = list(exception_accounts)

        # Step 1: 예약자 계정 잠금 해제
        if reservation.account_name:
            unlock_result = SessionManager.unlock_user(server, reservation.account_name)
            result["steps"].append({
                "step": "unlock_reservee",
                "ok": unlock_result.ok,
                "message": unlock_result.message,
                "details": unlock_result.details
            })
            if not unlock_result.ok:
                logger.error(f"Failed to unlock reservee account: {unlock_result.message}")
        else:
            logger.warning(f"Reservation {reservation.id} has no account_name, skipping unlock")
            result["steps"].append({
                "step": "unlock_reservee",
                "ok": False,
                "message": "No account_name specified in reservation",
            })

        # Step 2: 예외 계정 제외 모든 계정 잠금
        lock_result = SessionManager.lock_all_except(server, exception_accounts)
        result["steps"].append({
            "step": "lock_others",
            "ok": lock_result.ok,
            "message": lock_result.message,
            "details": lock_result.details
        })
        if not lock_result.ok:
            logger.warning(f"Some accounts failed to lock: {lock_result.details}")

        # Step 3: 예외 계정 제외 모든 프로세스 종료 (클린업)
        kill_result = SessionManager.kill_processes_except(server, exception_accounts)
        result["steps"].append({
            "step": "kill_processes",
            "ok": kill_result.ok,
            "message": kill_result.message,
            "details": kill_result.details
        })
        if not kill_result.ok:
            logger.warning(f"Some processes failed to kill: {kill_result.details}")

        # 전체 성공 여부 판단
        all_ok = all(step["ok"] for step in result["steps"] if step.get("ok") is not None)
        result["success"] = all_ok

        logger.info(f"Reservation {reservation.id} activation {'succeeded' if all_ok else 'completed with errors'}")
        return result

    @staticmethod
    async def deactivate_reservation(db: AsyncSession, reservation: Reservation) -> dict:
        """
        예약 비활성화 - 예약 종료 시 실행
        
        1. 예약자 프로세스 강제 종료 (SIGKILL)
        2. 예약자 계정 잠금
        
        Args:
            db: 데이터베이스 세션
            reservation: 예약 객체
            
        Returns:
            실행 결과 딕셔너리
        """
        logger.info(f"Deactivating reservation {reservation.id} for '{reservation.account_name}' on '{reservation.server_resource.name}'")

        server = reservation.server_resource
        result = {
            "reservation_id": str(reservation.id),
            "account_name": reservation.account_name,
            "server_name": server.name,
            "steps": []
        }

        if not reservation.account_name:
            logger.warning(f"Reservation {reservation.id} has no account_name, skipping deactivation")
            result["steps"].append({
                "step": "deactivate",
                "ok": False,
                "message": "No account_name specified in reservation",
            })
            result["success"] = False
            return result

        # Step 1: 예약자 프로세스 강제 종료 (SIGKILL)
        kill_result = SessionManager.kill_user_processes(
            server,
            reservation.account_name,
            force=True  # SIGKILL
        )
        result["steps"].append({
            "step": "kill_processes",
            "ok": kill_result.ok,
            "message": kill_result.message,
            "details": kill_result.details
        })
        if not kill_result.ok:
            logger.warning(f"Failed to kill processes for '{reservation.account_name}': {kill_result.message}")

        # Step 2: 예약자 계정 잠금
        lock_result = SessionManager.lock_user(server, reservation.account_name)
        result["steps"].append({
            "step": "lock_user",
            "ok": lock_result.ok,
            "message": lock_result.message,
            "details": lock_result.details
        })
        if not lock_result.ok:
            logger.error(f"Failed to lock user '{reservation.account_name}': {lock_result.message}")

        # 전체 성공 여부 판단
        all_ok = all(step["ok"] for step in result["steps"])
        result["success"] = all_ok

        logger.info(f"Reservation {reservation.id} deactivation {'succeeded' if all_ok else 'completed with errors'}")
        return result

    @staticmethod
    async def process_reservation_events() -> dict:
        """
        스케줄러 메인 로직 - 예약 시작/종료 이벤트 처리
        
        매 1분마다 실행되며:
        1. 시작할 예약 찾아서 활성화
        2. 종료할 예약 찾아서 비활성화
        
        Returns:
            처리 결과 요약
        """
        logger.info("Processing reservation events...")
        
        async with async_session_factory() as db:
            now = datetime.now(timezone.utc)
            summary = {
                "timestamp": now.isoformat(),
                "activated": [],
                "deactivated": [],
                "errors": []
            }

            try:
                # 1. 시작할 예약 찾기
                # 조건: start_at <= now < end_at, status = active, 아직 활성화 안 됨
                starting_stmt = (
                    select(Reservation)
                    .where(
                        Reservation.start_at <= now,
                        Reservation.end_at > now,
                        Reservation.status == ReservationStatus.ACTIVE,
                    )
                    .order_by(Reservation.start_at)
                )
                result = await db.execute(starting_stmt)
                starting_reservations = result.scalars().all()

                for reservation in starting_reservations:
                    # 이미 활성화되었는지 확인 (중복 방지)
                    if await SessionScheduler.has_event_logged(
                        db,
                        reservation.id,
                        SessionEventType.ACTIVATED
                    ):
                        logger.debug(f"Reservation {reservation.id} already activated, skipping")
                        continue

                    try:
                        activation_result = await SessionScheduler.activate_reservation(db, reservation)
                        
                        # 로그 기록
                        await SessionScheduler.log_event(
                            db,
                            reservation.id,
                            SessionEventType.ACTIVATED if activation_result["success"] else SessionEventType.ERROR,
                            activation_result
                        )
                        
                        summary["activated"].append({
                            "reservation_id": str(reservation.id),
                            "success": activation_result["success"]
                        })
                    except Exception as e:
                        logger.error(f"Error activating reservation {reservation.id}: {e}", exc_info=True)
                        summary["errors"].append({
                            "reservation_id": str(reservation.id),
                            "operation": "activate",
                            "error": str(e)
                        })
                        
                        # 에러 로그 기록
                        await SessionScheduler.log_event(
                            db,
                            reservation.id,
                            SessionEventType.ERROR,
                            {"error": str(e), "operation": "activate"}
                        )

                # 2. 종료할 예약 찾기
                # 조건: end_at <= now, status = active, 아직 비활성화 안 됨
                ending_stmt = (
                    select(Reservation)
                    .where(
                        Reservation.end_at <= now,
                        Reservation.status == ReservationStatus.ACTIVE,
                    )
                    .order_by(Reservation.end_at)
                )
                result = await db.execute(ending_stmt)
                ending_reservations = result.scalars().all()

                for reservation in ending_reservations:
                    # 이미 비활성화되었는지 확인 (중복 방지)
                    if await SessionScheduler.has_event_logged(
                        db,
                        reservation.id,
                        SessionEventType.DEACTIVATED
                    ):
                        logger.debug(f"Reservation {reservation.id} already deactivated, skipping")
                        continue

                    try:
                        deactivation_result = await SessionScheduler.deactivate_reservation(db, reservation)
                        
                        # 로그 기록
                        await SessionScheduler.log_event(
                            db,
                            reservation.id,
                            SessionEventType.DEACTIVATED if deactivation_result["success"] else SessionEventType.ERROR,
                            deactivation_result
                        )
                        
                        summary["deactivated"].append({
                            "reservation_id": str(reservation.id),
                            "success": deactivation_result["success"]
                        })
                    except Exception as e:
                        logger.error(f"Error deactivating reservation {reservation.id}: {e}", exc_info=True)
                        summary["errors"].append({
                            "reservation_id": str(reservation.id),
                            "operation": "deactivate",
                            "error": str(e)
                        })
                        
                        # 에러 로그 기록
                        await SessionScheduler.log_event(
                            db,
                            reservation.id,
                            SessionEventType.ERROR,
                            {"error": str(e), "operation": "deactivate"}
                        )

                logger.info(
                    f"Event processing completed: "
                    f"{len(summary['activated'])} activated, "
                    f"{len(summary['deactivated'])} deactivated, "
                    f"{len(summary['errors'])} errors"
                )

            except Exception as e:
                logger.error(f"Fatal error in process_reservation_events: {e}", exc_info=True)
                summary["errors"].append({
                    "operation": "scheduler",
                    "error": str(e)
                })

            return summary
