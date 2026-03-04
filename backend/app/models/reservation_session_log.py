import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SessionEventType(str, enum.Enum):
    ACTIVATED = "activated"
    DEACTIVATED = "deactivated"
    ERROR = "error"


class ReservationSessionLog(Base):
    __tablename__ = "reservation_session_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # 기존 컬럼: 단일 예약 호환성을 위해 유지 (nullable로 변경)
    reservation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reservations.id"), nullable=True
    )

    # 신규 컬럼: instance 기반 로깅 (migration 010에서 추가됨)
    reservation_instance_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("reservation_instances.id", ondelete="SET NULL"),
        nullable=True,
    )

    event_type: Mapped[SessionEventType] = mapped_column(
        Enum(
            SessionEventType,
            name="session_event_type",
            native_enum=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    reservation = relationship("Reservation", lazy="selectin", foreign_keys=[reservation_id])
    instance = relationship(
        "ReservationInstance", lazy="selectin", foreign_keys=[reservation_instance_id]
    )

    def __repr__(self) -> str:
        return f"<ReservationSessionLog {self.event_type} instance={self.reservation_instance_id}>"

