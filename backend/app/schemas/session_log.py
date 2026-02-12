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

    model_config = {"from_attributes": True}
