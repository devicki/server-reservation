"""Serve cases API — Local LLM serve 성공 사례 공유."""
import uuid

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.serve_case import ServeCase
from app.models.user import User
from app.schemas.serve_case import (
    ServeCaseCreateRequest,
    ServeCaseListResponse,
    ServeCaseResponse,
)

router = APIRouter(prefix="/serve-cases", tags=["Serve Cases"])


def _to_response(c: ServeCase) -> ServeCaseResponse:
    return ServeCaseResponse(
        id=c.id,
        user_id=c.user_id,
        user_name=c.user.name if c.user else "Unknown",
        server_resource_id=c.server_resource_id,
        server_name=c.server_resource.name if c.server_resource else "Unknown",
        model_name=c.model_name,
        model_info=c.model_info,
        serve_command=c.serve_command,
        resource_allocation=c.resource_allocation,
        notes=c.notes,
        created_at=c.created_at,
    )


@router.post("/", response_model=ServeCaseResponse, status_code=201)
async def create_serve_case(
    body: ServeCaseCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Local LLM serve 성공 사례 등록 (로그인 사용자)."""
    case = ServeCase(
        user_id=current_user.id,
        server_resource_id=body.server_resource_id,
        model_name=body.model_name,
        model_info=body.model_info,
        serve_command=body.serve_command,
        resource_allocation=body.resource_allocation,
        notes=body.notes,
    )
    db.add(case)
    await db.commit()
    await db.refresh(case)
    result = await db.execute(
        select(ServeCase)
        .options(
            selectinload(ServeCase.user),
            selectinload(ServeCase.server_resource),
        )
        .where(ServeCase.id == case.id)
    )
    case_loaded = result.scalar_one()
    return _to_response(case_loaded)


@router.get("/", response_model=ServeCaseListResponse)
async def list_serve_cases(
    limit: int = Query(default=50, le=100, ge=1),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """사례 목록 (최신순)."""
    count_stmt = select(func.count(ServeCase.id))
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(ServeCase)
        .options(
            selectinload(ServeCase.user),
            selectinload(ServeCase.server_resource),
        )
        .order_by(ServeCase.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    items = list(result.scalars().all())
    return ServeCaseListResponse(
        items=[_to_response(c) for c in items],
        total=total,
    )


@router.get("/{serve_case_id}", response_model=ServeCaseResponse)
async def get_serve_case(
    serve_case_id: uuid.UUID = Path(..., description="사례 ID"),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """사례 상세 조회."""
    result = await db.execute(
        select(ServeCase)
        .options(
            selectinload(ServeCase.user),
            selectinload(ServeCase.server_resource),
        )
        .where(ServeCase.id == serve_case_id)
    )
    case = result.scalar_one_or_none()
    if not case:
        raise NotFoundError("사례를 찾을 수 없습니다.")
    return _to_response(case)
