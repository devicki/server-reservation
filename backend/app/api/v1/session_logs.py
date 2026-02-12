"""Session logs API - 예약 세션 활성화/비활성화 로그 조회"""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_admin
from app.database import get_db
from app.models.reservation_session_log import ReservationSessionLog
from app.models.user import User
from app.schemas.session_log import SessionLogResponse

router = APIRouter(prefix="/session-logs", tags=["Session Logs"])


@router.get("/", response_model=list[SessionLogResponse])
async def list_session_logs(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_admin)],  # Admin only
    reservation_id: uuid.UUID | None = Query(None, description="Filter by reservation ID"),
    limit: int = Query(50, ge=1, le=100, description="Number of logs to return"),
    offset: int = Query(0, ge=0, description="Number of logs to skip"),
):
    """
    세션 로그 목록 조회 (관리자 전용)
    
    예약의 활성화/비활성화 이벤트 로그를 조회합니다.
    """
    conditions = []
    if reservation_id:
        conditions.append(ReservationSessionLog.reservation_id == reservation_id)

    stmt = (
        select(ReservationSessionLog)
        .where(*conditions)
        .order_by(ReservationSessionLog.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    
    result = await db.execute(stmt)
    logs = result.scalars().all()
    
    return logs


@router.get("/reservation/{reservation_id}", response_model=list[SessionLogResponse])
async def get_reservation_session_logs(
    reservation_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    특정 예약의 세션 로그 조회
    
    자신의 예약 또는 관리자는 모든 예약의 로그를 조회할 수 있습니다.
    """
    # TODO: 권한 체크 (예약 소유자 또는 관리자만)
    # 현재는 로그인한 사용자면 모두 조회 가능
    
    stmt = (
        select(ReservationSessionLog)
        .where(ReservationSessionLog.reservation_id == reservation_id)
        .order_by(ReservationSessionLog.created_at.desc())
    )
    
    result = await db.execute(stmt)
    logs = result.scalars().all()
    
    return logs
