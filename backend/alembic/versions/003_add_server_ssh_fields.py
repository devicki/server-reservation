"""Add SSH connection fields to server_resources for remote command execution

Revision ID: 003
Revises: 002
Create Date: 2026-02-12

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "server_resources",
        sa.Column("host", sa.String(255), nullable=True),
    )
    op.add_column(
        "server_resources",
        sa.Column("ssh_port", sa.Integer(), nullable=False, server_default="22"),
    )
    op.add_column(
        "server_resources",
        sa.Column("ssh_username", sa.String(100), nullable=True),
    )
    op.add_column(
        "server_resources",
        sa.Column("ssh_private_key", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("server_resources", "ssh_private_key")
    op.drop_column("server_resources", "ssh_username")
    op.drop_column("server_resources", "ssh_port")
    op.drop_column("server_resources", "host")
