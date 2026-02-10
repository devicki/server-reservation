"""Initial schema - users, server_resources, reservations

Revision ID: 001
Revises: None
Create Date: 2026-02-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable btree_gist extension for EXCLUDE constraint
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    # Create user_role enum
    user_role = postgresql.ENUM("user", "admin", name="user_role", create_type=False)
    user_role.create(op.get_bind(), checkfirst=True)

    # Create reservation_status enum
    reservation_status = postgresql.ENUM(
        "active", "canceled", name="reservation_status", create_type=False
    )
    reservation_status.create(op.get_bind(), checkfirst=True)

    # Users table
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("role", user_role, nullable=False, server_default="user"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # Server resources table
    op.create_table(
        "server_resources",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("capacity", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
    )

    # Reservations table
    op.create_table(
        "reservations",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("server_resource_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", reservation_status, nullable=False, server_default="active"),
        sa.Column("google_event_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["server_resource_id"], ["server_resources.id"]),
        sa.CheckConstraint("end_at > start_at", name="valid_time_range"),
    )
    op.create_index("idx_reservations_server_time", "reservations", ["server_resource_id", "start_at", "end_at"])
    op.create_index("idx_reservations_user", "reservations", ["user_id"])

    # EXCLUDE constraint to prevent overlapping active reservations on the same server
    op.execute("""
        ALTER TABLE reservations ADD CONSTRAINT no_overlapping_reservations
        EXCLUDE USING gist (
            server_resource_id WITH =,
            tstzrange(start_at, end_at) WITH &&
        ) WHERE (status = 'active')
    """)


def downgrade() -> None:
    op.drop_table("reservations")
    op.drop_table("server_resources")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS reservation_status")
    op.execute("DROP TYPE IF EXISTS user_role")
    op.execute("DROP EXTENSION IF EXISTS btree_gist")
