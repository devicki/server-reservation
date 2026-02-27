"""Serve case model — Local LLM serve 성공 사례 공유."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ServeCase(Base):
    """예약 서버에서 local LLM 모델 serve 성공 사례."""

    __tablename__ = "serve_cases"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    server_resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("server_resources.id", ondelete="CASCADE"),
        nullable=False,
    )
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    model_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    serve_command: Mapped[str] = mapped_column(Text, nullable=False)
    resource_allocation: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    user = relationship("User", back_populates="serve_cases", lazy="selectin")
    server_resource = relationship(
        "ServerResource", back_populates="serve_cases", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<ServeCase {self.model_name} @ {self.server_resource_id}>"
