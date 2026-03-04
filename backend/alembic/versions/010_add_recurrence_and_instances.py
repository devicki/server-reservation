"""Add recurrence support: recurrence_rules, reservation_instances, alter reservations

Revision ID: 010
Revises: 009
Create Date: 2026-03-03

변경 사항:
1. recurrence_rules 테이블 신규 생성
2. reservations 테이블 수정
   - start_at / end_at → nullable 허용 (반복 예약은 instances로 관리)
   - valid_time_range 제약 조건 교체 (NULL 허용)
   - recurrence_rule_id FK 컬럼 추가
3. reservation_instances 테이블 신규 생성
   - btree_gist 확장 설치
   - EXCLUDE USING gist 제약으로 서버별 시간 중복 방지
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # 0. btree_gist 확장 (EXCLUDE USING gist 제약에 필요)
    # ------------------------------------------------------------------ #
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    # ------------------------------------------------------------------ #
    # 1. recurrence_rules 테이블
    # ------------------------------------------------------------------ #
    op.create_table(
        "recurrence_rules",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("freq", sa.String(20), nullable=False),
        sa.Column("interval", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("by_day", sa.String(50), nullable=True),
        sa.Column("by_month_day", sa.Integer(), nullable=True),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # ------------------------------------------------------------------ #
    # 2. reservations 테이블 변경
    # ------------------------------------------------------------------ #

    # 2-a. 기존 valid_time_range 제약 삭제
    op.drop_constraint("valid_time_range", "reservations", type_="check")

    # 2-b. start_at / end_at nullable 허용
    op.alter_column("reservations", "start_at", nullable=True)
    op.alter_column("reservations", "end_at", nullable=True)

    # 2-c. NULL을 허용하는 새 check 제약 추가
    op.create_check_constraint(
        "valid_time_range",
        "reservations",
        "(start_at IS NULL OR end_at IS NULL OR end_at > start_at)",
    )

    # 2-d. recurrence_rule_id FK 컬럼 추가
    op.add_column(
        "reservations",
        sa.Column(
            "recurrence_rule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("recurrence_rules.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_reservations_recurrence", "reservations", ["recurrence_rule_id"]
    )

    # ------------------------------------------------------------------ #
    # 3. reservation_instances 테이블
    # ------------------------------------------------------------------ #
    # status 컬럼은 기존 reservation_status enum 타입을 재사용한다.
    # sa.Enum()을 create_table 안에 넣으면 create_type=False 지정에도
    # before_create 이벤트가 타입 재생성을 시도하므로 VARCHAR로 선언 후
    # ALTER COLUMN으로 타입을 전환한다.
    op.create_table(
        "reservation_instances",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("reservation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("server_resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["reservation_id"],
            ["reservations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["server_resource_id"],
            ["server_resources.id"],
        ),
        sa.CheckConstraint("end_at > start_at", name="ri_valid_time_range"),
    )

    # status 컬럼을 기존 reservation_status enum 타입으로 전환
    # server_default('active'::varchar)가 남아 있으면 타입 전환 시 충돌하므로
    # default 제거 → 타입 전환 → default 재설정 순서로 처리한다.
    op.execute(
        "ALTER TABLE reservation_instances ALTER COLUMN status DROP DEFAULT"
    )
    op.execute("""
        ALTER TABLE reservation_instances
        ALTER COLUMN status TYPE reservation_status
        USING status::reservation_status
    """)
    op.execute(
        "ALTER TABLE reservation_instances ALTER COLUMN status SET DEFAULT 'active'"
    )

    op.create_index(
        "idx_reservation_instances_server_time",
        "reservation_instances",
        ["server_resource_id", "start_at", "end_at"],
    )
    op.create_index(
        "idx_reservation_instances_reservation",
        "reservation_instances",
        ["reservation_id"],
    )
    op.create_index(
        "idx_reservation_instances_status",
        "reservation_instances",
        ["status"],
    )

    # 3-a. EXCLUDE 제약: 동일 서버에서 시간 겹침 금지 (DB 레벨 중복 방지 핵심)
    op.execute("""
        ALTER TABLE reservation_instances
        ADD CONSTRAINT no_overlap_per_server
        EXCLUDE USING gist (
            server_resource_id WITH =,
            tstzrange(start_at, end_at, '[)') WITH &&
        )
        WHERE (status = 'active')
    """)


    # ------------------------------------------------------------------ #
    # 4. reservation_session_logs 테이블: instance 기반 로깅 지원
    # ------------------------------------------------------------------ #
    # 기존 reservation_id를 nullable로 변경
    op.alter_column("reservation_session_logs", "reservation_id", nullable=True)

    # reservation_instance_id 컬럼 추가
    op.add_column(
        "reservation_session_logs",
        sa.Column(
            "reservation_instance_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("reservation_instances.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_session_logs_instance_id",
        "reservation_session_logs",
        ["reservation_instance_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_session_logs_instance_id", table_name="reservation_session_logs")
    op.drop_column("reservation_session_logs", "reservation_instance_id")
    op.alter_column("reservation_session_logs", "reservation_id", nullable=False)

    op.execute(
        "ALTER TABLE reservation_instances DROP CONSTRAINT IF EXISTS no_overlap_per_server"
    )

    # status 컬럼을 VARCHAR로 되돌린 뒤 테이블 삭제
    op.execute("""
        ALTER TABLE reservation_instances
        ALTER COLUMN status TYPE VARCHAR(20)
    """)

    op.drop_index("idx_reservation_instances_status", table_name="reservation_instances")
    op.drop_index(
        "idx_reservation_instances_reservation", table_name="reservation_instances"
    )
    op.drop_index(
        "idx_reservation_instances_server_time", table_name="reservation_instances"
    )
    op.drop_table("reservation_instances")

    op.drop_index("idx_reservations_recurrence", table_name="reservations")
    op.drop_column("reservations", "recurrence_rule_id")

    op.drop_constraint("valid_time_range", "reservations", type_="check")
    op.alter_column("reservations", "start_at", nullable=False)
    op.alter_column("reservations", "end_at", nullable=False)
    op.create_check_constraint(
        "valid_time_range", "reservations", "end_at > start_at"
    )

    op.drop_table("recurrence_rules")
