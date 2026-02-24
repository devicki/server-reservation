"""Add feedback_comments and feedback_reactions tables

Revision ID: 008
Revises: 007
Create Date: 2026-02-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "feedback_comments",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("feedback_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["feedback_id"], ["feedback.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_feedback_comments_feedback_id", "feedback_comments", ["feedback_id"])
    op.create_index("ix_feedback_comments_user_id", "feedback_comments", ["user_id"])
    op.create_index("ix_feedback_comments_created_at", "feedback_comments", ["created_at"])

    op.execute("""
        DO $$ BEGIN
            CREATE TYPE feedback_reaction_type AS ENUM ('like');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    reaction_type_enum = postgresql.ENUM(
        "like", name="feedback_reaction_type", create_type=False
    )
    op.create_table(
        "feedback_reactions",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("feedback_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("reaction_type", reaction_type_enum, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["feedback_id"], ["feedback.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("feedback_id", "user_id", name="uq_feedback_reaction_user"),
    )
    op.create_index("ix_feedback_reactions_feedback_id", "feedback_reactions", ["feedback_id"])
    op.create_index("ix_feedback_reactions_user_id", "feedback_reactions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_feedback_reactions_user_id", table_name="feedback_reactions")
    op.drop_index("ix_feedback_reactions_feedback_id", table_name="feedback_reactions")
    op.drop_table("feedback_reactions")
    op.execute("DROP TYPE IF EXISTS feedback_reaction_type")

    op.drop_index("ix_feedback_comments_created_at", table_name="feedback_comments")
    op.drop_index("ix_feedback_comments_user_id", table_name="feedback_comments")
    op.drop_index("ix_feedback_comments_feedback_id", table_name="feedback_comments")
    op.drop_table("feedback_comments")
