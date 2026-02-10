from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.database import get_db
from app.models.feedback import Feedback
from app.models.user import User
from app.schemas.feedback import (
    FeedbackCreateRequest,
    FeedbackListResponse,
    FeedbackResponse,
)

router = APIRouter(prefix="/feedback", tags=["Feedback"])


def _to_response(fb: Feedback) -> FeedbackResponse:
    return FeedbackResponse(
        id=fb.id,
        user_id=fb.user_id,
        user_name=fb.user.name if fb.user else "Unknown",
        content=fb.content,
        created_at=fb.created_at,
    )


@router.post("/", response_model=FeedbackResponse, status_code=201)
async def create_feedback(
    body: FeedbackCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """시스템 개선 의견 등록 (로그인 사용자)."""
    feedback = Feedback(
        user_id=current_user.id,
        content=body.content,
    )
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)
    result = await db.execute(
        select(Feedback).options(selectinload(Feedback.user)).where(Feedback.id == feedback.id)
    )
    feedback_loaded = result.scalar_one()
    return _to_response(feedback_loaded)


@router.get("/", response_model=FeedbackListResponse)
async def list_feedback(
    limit: int = Query(default=50, le=100, ge=1),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """시스템 개선 의견 목록 (최신순)."""
    count_stmt = select(func.count(Feedback.id))
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(Feedback)
        .options(selectinload(Feedback.user))
        .order_by(Feedback.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    items = list(result.scalars().all())
    return FeedbackListResponse(
        items=[_to_response(fb) for fb in items],
        total=total,
    )