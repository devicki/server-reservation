"""Add reservation_session_logs table for tracking session activation/deactivation events

Revision ID: 006
Revises: 005
Create Date: 2026-02-12

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create session_event_type enum if it doesn't exist
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE session_event_type AS ENUM ('activated', 'deactivated', 'error');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    # Use dialect ENUM that does not emit CREATE TYPE (type already created above)
    session_event_type_enum = postgresql.ENUM(
        "activated", "deactivated", "error",
        name="session_event_type",
        create_type=False,
    )
    
    # Create reservation_session_logs table
    op.create_table(
        "reservation_session_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("reservation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", session_event_type_enum, nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["reservation_id"], ["reservations.id"], ondelete="CASCADE"),
    )
    
    # Create index for efficient lookup
    op.create_index(
        "idx_session_logs_reservation",
        "reservation_session_logs",
        ["reservation_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_session_logs_reservation", table_name="reservation_session_logs")
    op.drop_table("reservation_session_logs")
    # Drop the enum type if it exists
    op.execute("DROP TYPE IF EXISTS session_event_type")
