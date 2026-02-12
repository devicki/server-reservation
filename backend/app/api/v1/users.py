import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_current_user
from app.core.exceptions import BadRequestError, NotFoundError
from app.database import get_db
from app.models.user import User, UserRole
from app.schemas.auth import UserResponse
from app.schemas.user import UserListResponse, UserUpdateRequest

router = APIRouter(prefix="/users", tags=["Users (Admin)"])


@router.get("/", response_model=UserListResponse)
async def list_users(
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """사용자 목록 (관리자 전용)."""
    count_stmt = select(func.count(User.id))
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = select(User).order_by(User.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    users = list(result.scalars().all())

    return UserListResponse(
        items=[UserResponse.model_validate(u) for u in users],
        total=total,
    )


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """사용자 역할/활성 상태 변경 (관리자 전용). 마지막 admin은 강등 불가."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise NotFoundError("User not found")

    if body.role is not None:
        if user.id == current_user.id and body.role != UserRole.ADMIN:
            admin_count = await db.execute(
                select(func.count(User.id)).where(User.role == UserRole.ADMIN)
            )
            if (admin_count.scalar() or 0) <= 1:
                raise BadRequestError("Cannot demote the last admin")
        user.role = body.role

    if body.is_active is not None:
        if user.id == current_user.id and not body.is_active:
            raise BadRequestError("Cannot deactivate your own account")
        user.is_active = body.is_active

    await db.commit()
    await db.refresh(user)
    return user
