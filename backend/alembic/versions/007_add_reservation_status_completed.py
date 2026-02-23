"""Add reservation_status enum value 'completed' for ended reservations

Revision ID: 007
Revises: 006
Create Date: 2026-02-23

"""
from typing import Sequence, Union

from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add 'completed' to reservation_status enum (ignore if already present)
    op.execute("""
        DO $$ BEGIN
            ALTER TYPE reservation_status ADD VALUE 'completed';
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)


def downgrade() -> None:
    # PostgreSQL does not support removing enum values; would require recreating type.
    # Leaving no-op: existing 'completed' rows would need manual migration to 'active' first.
    pass
