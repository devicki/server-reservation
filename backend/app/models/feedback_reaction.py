import enum
import uuid

from sqlalchemy import Enum, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class FeedbackReactionType(str, enum.Enum):
    LIKE = "like"


class FeedbackReaction(Base):
    """의견 게시판 반응 (사용자당 의견당 1개)."""

    __tablename__ = "feedback_reactions"
    __table_args__ = (
        UniqueConstraint("feedback_id", "user_id", name="uq_feedback_reaction_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    feedback_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("feedback.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    reaction_type: Mapped[FeedbackReactionType] = mapped_column(
        Enum(
            FeedbackReactionType,
            name="feedback_reaction_type",
            native_enum=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )

    feedback = relationship("Feedback", back_populates="reactions", lazy="selectin")
    user = relationship("User", back_populates="feedback_reactions", lazy="selectin")

    def __repr__(self) -> str:
        return f"<FeedbackReaction {self.id}>"
