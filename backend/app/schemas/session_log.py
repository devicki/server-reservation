"""Session log schemas"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.reservation_session_log import SessionEventType


class SessionLogResponse(BaseModel):
    id: UUID
    reservation_id: UUID
    event_type: SessionEventType
    details: dict | None
    created_at: datetime
    # 예약 관련 추가 정보 (목록 가독성용)
    server_name: str | None = None
    reservation_title: str | None = None
    reservation_user_name: str | None = None

    model_config = {"from_attributes": True}
