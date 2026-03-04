"""Remove start_at, end_at from reservations table

Revision ID: 011
Revises: 010
Create Date: 2026-03-03

변경 사항:
- no_overlapping_reservations EXCLUDE 제약 제거 (start_at/end_at 참조)
- valid_time_range check 제약 제거
- idx_reservations_server_time 인덱스 제거
- reservations.start_at, end_at 컬럼 제거
- idx_reservations_server 인덱스 추가 (server_resource_id 단독)
- recurrence_rule_id 컬럼 추가 (010에서 미처리된 경우 IF NOT EXISTS로 보완)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. start_at/end_at에 의존하는 제약/인덱스를 먼저 제거 ──────────

    # 기존 EXCLUDE 제약 (start_at, end_at 참조)
    conn.execute(sa.text("""
        ALTER TABLE reservations
        DROP CONSTRAINT IF EXISTS no_overlapping_reservations
    """))

    # valid_time_range check 제약 (존재하면 제거)
    conn.execute(sa.text("""
        ALTER TABLE reservations
        DROP CONSTRAINT IF EXISTS valid_time_range
    """))

    # idx_reservations_server_time 인덱스 (start_at, end_at 포함)
    conn.execute(sa.text(
        "DROP INDEX IF EXISTS idx_reservations_server_time"
    ))

    # ── 2. 컬럼 제거 ──────────────────────────────────────────────────
    op.drop_column("reservations", "start_at")
    op.drop_column("reservations", "end_at")

    # ── 3. server_resource_id 단독 인덱스 추가 ────────────────────────
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_reservations_server "
        "ON reservations (server_resource_id)"
    ))

    # ── 4. recurrence_rule_id 컬럼 (010에서 누락된 경우 보완) ──────────
    conn.execute(sa.text("""
        ALTER TABLE reservations
        ADD COLUMN IF NOT EXISTS recurrence_rule_id UUID
        REFERENCES recurrence_rules(id) ON DELETE SET NULL
    """))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_reservations_recurrence "
        "ON reservations (recurrence_rule_id)"
    ))


def downgrade() -> None:
    conn = op.get_bind()

    conn.execute(sa.text("DROP INDEX IF EXISTS idx_reservations_recurrence"))
    conn.execute(sa.text(
        "ALTER TABLE reservations DROP COLUMN IF EXISTS recurrence_rule_id"
    ))
    conn.execute(sa.text("DROP INDEX IF EXISTS idx_reservations_server"))

    op.add_column(
        "reservations",
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "reservations",
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
    )

    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_reservations_server_time
        ON reservations (server_resource_id, start_at, end_at)
    """))
