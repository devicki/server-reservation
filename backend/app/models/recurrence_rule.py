import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class RecurrenceRule(Base):
    __tablename__ = "recurrence_rules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # DAILY / WEEKLY / MONTHLY
    freq: Mapped[str] = mapped_column(String(20), nullable=False)
    interval: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # WEEKLY: 쉼표 구분 요일 (예: "MON,WED,FRI")
    by_day: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # MONTHLY: 매월 몇 일 (예: 15)
    by_month_day: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 반복 시작/종료 날짜 (start_date는 첫 번째 instance의 날짜 기준)
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    reservations = relationship("Reservation", back_populates="recurrence_rule", lazy="select")

    def __repr__(self) -> str:
        return f"<RecurrenceRule {self.freq} interval={self.interval}>"
