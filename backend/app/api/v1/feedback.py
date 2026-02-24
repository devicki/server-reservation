import uuid

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.feedback import Feedback
from app.models.feedback_comment import FeedbackComment
from app.models.feedback_reaction import FeedbackReaction, FeedbackReactionType
from app.models.user import User
from app.schemas.feedback import (
    FeedbackCommentCreateRequest,
    FeedbackCommentResponse,
    FeedbackCreateRequest,
    FeedbackListResponse,
    FeedbackReactionSummary,
    FeedbackResponse,
)

router = APIRouter(prefix="/feedback", tags=["Feedback"])


def _comment_to_response(c: FeedbackComment) -> FeedbackCommentResponse:
    return FeedbackCommentResponse(
        id=c.id,
        feedback_id=c.feedback_id,
        user_id=c.user_id,
        user_name=c.user.name if c.user else "Unknown",
        content=c.content,
        created_at=c.created_at,
    )


def _to_response(fb: Feedback, current_user_id: uuid.UUID | None = None) -> FeedbackResponse:
    comments = sorted(fb.comments, key=lambda c: c.created_at) if fb.comments else []
    like_count = sum(1 for r in (fb.reactions or []) if r.reaction_type == FeedbackReactionType.LIKE)
    user_reaction = None
    if current_user_id and fb.reactions:
        for r in fb.reactions:
            if r.user_id == current_user_id and r.reaction_type == FeedbackReactionType.LIKE:
                user_reaction = "like"
                break
    return FeedbackResponse(
        id=fb.id,
        user_id=fb.user_id,
        user_name=fb.user.name if fb.user else "Unknown",
        content=fb.content,
        created_at=fb.created_at,
        comment_count=len(comments),
        comments=[_comment_to_response(c) for c in comments],
        reaction_counts=FeedbackReactionSummary(like=like_count),
        user_reaction=user_reaction,
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
        select(Feedback)
        .options(
            selectinload(Feedback.user),
            selectinload(Feedback.comments).selectinload(FeedbackComment.user),
            selectinload(Feedback.reactions),
        )
        .where(Feedback.id == feedback.id)
    )
    feedback_loaded = result.scalar_one()
    return _to_response(feedback_loaded, current_user.id)


@router.get("/", response_model=FeedbackListResponse)
async def list_feedback(
    limit: int = Query(default=50, le=100, ge=1),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """시스템 개선 의견 목록 (최신순, 댓글·반응 포함)."""
    count_stmt = select(func.count(Feedback.id))
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(Feedback)
        .options(
            selectinload(Feedback.user),
            selectinload(Feedback.comments).selectinload(FeedbackComment.user),
            selectinload(Feedback.reactions),
        )
        .order_by(Feedback.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    items = list(result.scalars().all())
    return FeedbackListResponse(
        items=[_to_response(fb, current_user.id) for fb in items],
        total=total,
    )


@router.post("/{feedback_id}/comments", response_model=FeedbackCommentResponse, status_code=201)
async def create_comment(
    feedback_id: uuid.UUID = Path(..., description="의견 ID"),
    body: FeedbackCommentCreateRequest = ...,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """의견에 댓글 등록."""
    result = await db.execute(select(Feedback).where(Feedback.id == feedback_id))
    feedback = result.scalar_one_or_none()
    if not feedback:
        raise NotFoundError("의견을 찾을 수 없습니다.")
    comment = FeedbackComment(
        feedback_id=feedback_id,
        user_id=current_user.id,
        content=body.content,
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    result = await db.execute(
        select(FeedbackComment)
        .options(selectinload(FeedbackComment.user))
        .where(FeedbackComment.id == comment.id)
    )
    comment_loaded = result.scalar_one()
    return _comment_to_response(comment_loaded)


@router.post("/{feedback_id}/reactions", response_model=FeedbackResponse)
async def toggle_reaction(
    feedback_id: uuid.UUID = Path(..., description="의견 ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """의견에 좋아요 반응 토글 (이미 누른 경우 해제)."""
    result = await db.execute(
        select(Feedback)
        .options(
            selectinload(Feedback.user),
            selectinload(Feedback.comments).selectinload(FeedbackComment.user),
            selectinload(Feedback.reactions),
        )
        .where(Feedback.id == feedback_id)
    )
    feedback = result.scalar_one_or_none()
    if not feedback:
        raise NotFoundError("의견을 찾을 수 없습니다.")
    existing = await db.execute(
        select(FeedbackReaction).where(
            FeedbackReaction.feedback_id == feedback_id,
            FeedbackReaction.user_id == current_user.id,
        )
    )
    reaction = existing.scalar_one_or_none()
    if reaction:
        await db.delete(reaction)
    else:
        new_reaction = FeedbackReaction(
            feedback_id=feedback_id,
            user_id=current_user.id,
            reaction_type=FeedbackReactionType.LIKE,
        )
        db.add(new_reaction)
    await db.commit()
    await db.refresh(feedback)
    result = await db.execute(
        select(Feedback)
        .options(
            selectinload(Feedback.user),
            selectinload(Feedback.comments).selectinload(FeedbackComment.user),
            selectinload(Feedback.reactions),
        )
        .where(Feedback.id == feedback_id)
    )
    feedback_loaded = result.scalar_one()
    return _to_response(feedback_loaded, current_user.id)
