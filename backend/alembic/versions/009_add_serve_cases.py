"""Add serve_cases table for LLM serve success case sharing

Revision ID: 009
Revises: 008
Create Date: 2026-02-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "serve_cases",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("server_resource_id", sa.UUID(), nullable=False),
        sa.Column("model_name", sa.String(200), nullable=False),
        sa.Column("model_info", sa.Text(), nullable=True),
        sa.Column("serve_command", sa.Text(), nullable=False),
        sa.Column("resource_allocation", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["server_resource_id"], ["server_resources.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_serve_cases_user_id", "serve_cases", ["user_id"])
    op.create_index("ix_serve_cases_server_resource_id", "serve_cases", ["server_resource_id"])
    op.create_index("ix_serve_cases_created_at", "serve_cases", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_serve_cases_created_at", table_name="serve_cases")
    op.drop_index("ix_serve_cases_server_resource_id", table_name="serve_cases")
    op.drop_index("ix_serve_cases_user_id", table_name="serve_cases")
    op.drop_table("serve_cases")
