import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_current_user
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.server_resource import ServerResource
from app.models.user import User
from app.schemas.resource import (
    ResourceCreateRequest,
    ResourceListResponse,
    ResourceResponse,
    ResourceUpdateRequest,
)

router = APIRouter(prefix="/resources", tags=["Server Resources"])


@router.get("/", response_model=ResourceListResponse)
async def list_resources(
    is_active: bool | None = True,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """List all server resources."""
    conditions = []
    if is_active is not None:
        conditions.append(ServerResource.is_active == is_active)

    count_stmt = select(func.count(ServerResource.id)).where(*conditions)
    total = (await db.execute(count_stmt)).scalar()

    stmt = (
        select(ServerResource)
        .where(*conditions)
        .order_by(ServerResource.name)
    )
    result = await db.execute(stmt)
    resources = list(result.scalars().all())

    return ResourceListResponse(
        items=[ResourceResponse.model_validate(r) for r in resources],
        total=total,
    )


@router.get("/{resource_id}", response_model=ResourceResponse)
async def get_resource(
    resource_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """Get a specific server resource."""
    result = await db.execute(
        select(ServerResource).where(ServerResource.id == resource_id)
    )
    resource = result.scalar_one_or_none()
    if resource is None:
        raise NotFoundError("Server resource not found")
    return resource


@router.post("/", response_model=ResourceResponse, status_code=201)
async def create_resource(
    body: ResourceCreateRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """Create a new server resource. Admin only."""
    resource = ServerResource(
        name=body.name,
        description=body.description,
        capacity=body.capacity,
    )
    db.add(resource)
    await db.commit()
    await db.refresh(resource)
    return resource


@router.put("/{resource_id}", response_model=ResourceResponse)
async def update_resource(
    resource_id: uuid.UUID,
    body: ResourceUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """Update a server resource. Admin only."""
    result = await db.execute(
        select(ServerResource).where(ServerResource.id == resource_id)
    )
    resource = result.scalar_one_or_none()
    if resource is None:
        raise NotFoundError("Server resource not found")

    if body.name is not None:
        resource.name = body.name
    if body.description is not None:
        resource.description = body.description
    if body.capacity is not None:
        resource.capacity = body.capacity
    if body.is_active is not None:
        resource.is_active = body.is_active

    await db.commit()
    await db.refresh(resource)
    return resource


@router.delete("/{resource_id}", status_code=204)
async def delete_resource(
    resource_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """Soft-delete a server resource. Admin only."""
    result = await db.execute(
        select(ServerResource).where(ServerResource.id == resource_id)
    )
    resource = result.scalar_one_or_none()
    if resource is None:
        raise NotFoundError("Server resource not found")

    resource.is_active = False
    await db.commit()
