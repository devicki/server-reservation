"""Add account_exclusions to server_resources for excluding OS accounts from reservation list

Revision ID: 005
Revises: 004
Create Date: 2026-02-12

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "server_resources",
        sa.Column("account_exclusions", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("server_resources", "account_exclusions")
