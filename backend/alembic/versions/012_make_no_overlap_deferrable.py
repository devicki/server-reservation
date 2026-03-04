"""Make no_overlap_per_server EXCLUDE constraint DEFERRABLE INITIALLY DEFERRED

Revision ID: 012
Revises: 011
Create Date: 2026-03-04

변경 사항:
- no_overlap_per_server EXCLUDE 제약을 DEFERRABLE INITIALLY DEFERRED로 재생성.
  반복 예약의 이후 일정 일괄 수정 시, 같은 트랜잭션 내 중간 UPDATE 상태에서
  자기 자신의 기존 시간과 겹치는 것으로 오탐하는 문제 해결.
  DEFERRABLE INITIALLY DEFERRED 설정 시 제약 검사가 commit 시점으로 미뤄지므로
  트랜잭션 내 모든 UPDATE 완료 후 최종 상태만 검사한다.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE reservation_instances
        DROP CONSTRAINT IF EXISTS no_overlap_per_server
    """)
    op.execute("""
        ALTER TABLE reservation_instances
        ADD CONSTRAINT no_overlap_per_server
        EXCLUDE USING gist (
            server_resource_id WITH =,
            tstzrange(start_at, end_at, '[)') WITH &&
        )
        WHERE (status = 'active')
        DEFERRABLE INITIALLY DEFERRED
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE reservation_instances
        DROP CONSTRAINT IF EXISTS no_overlap_per_server
    """)
    op.execute("""
        ALTER TABLE reservation_instances
        ADD CONSTRAINT no_overlap_per_server
        EXCLUDE USING gist (
            server_resource_id WITH =,
            tstzrange(start_at, end_at, '[)') WITH &&
        )
        WHERE (status = 'active')
    """)
