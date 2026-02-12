import asyncio
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_current_user
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.server_resource import ServerResource
from app.models.user import User, UserRole
from app.schemas.resource import (
    ResourceCreateRequest,
    ResourceListResponse,
    ResourceResponse,
    ResourceTestConnectionResponse,
    ResourceUpdateRequest,
)
from app.services.ssh_runner import run_command

router = APIRouter(prefix="/resources", tags=["Server Resources"])


def _mask_ssh_key(r: ServerResource) -> ResourceResponse:
    resp = ResourceResponse.model_validate(r)
    resp.ssh_private_key = None
    return resp


@router.get("/", response_model=ResourceListResponse)
async def list_resources(
    is_active: bool | None = True,
    include_inactive: bool = Query(False, description="If true, list all (admin use)"),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """List server resources. SSH key is never returned in list."""
    conditions = []
    if not include_inactive and is_active is not None:
        conditions.append(ServerResource.is_active == is_active)

    count_stmt = select(func.count(ServerResource.id))
    if conditions:
        count_stmt = count_stmt.where(*conditions)
    total = (await db.execute(count_stmt)).scalar()

    stmt = select(ServerResource).order_by(ServerResource.name)
    if conditions:
        stmt = stmt.where(*conditions)
    result = await db.execute(stmt)
    resources = list(result.scalars().all())

    return ResourceListResponse(
        items=[_mask_ssh_key(r) for r in resources],
        total=total,
    )


@router.get("/{resource_id}", response_model=ResourceResponse)
async def get_resource(
    resource_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific server resource. Admin only gets ssh_private_key."""
    result = await db.execute(
        select(ServerResource).where(ServerResource.id == resource_id)
    )
    resource = result.scalar_one_or_none()
    if resource is None:
        raise NotFoundError("Server resource not found")
    resp = ResourceResponse.model_validate(resource)
    if current_user.role != UserRole.ADMIN:
        resp.ssh_private_key = None
    return resp


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
        host=body.host,
        ssh_port=body.ssh_port,
        ssh_username=body.ssh_username,
        ssh_private_key=body.ssh_private_key,
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
    if body.host is not None:
        resource.host = body.host
    if body.ssh_port is not None:
        resource.ssh_port = body.ssh_port
    if body.ssh_username is not None:
        resource.ssh_username = body.ssh_username
    if body.ssh_private_key is not None:
        resource.ssh_private_key = body.ssh_private_key

    await db.commit()
    await db.refresh(resource)
    return resource


@router.delete("/{resource_id}", status_code=204)
async def delete_resource(
    resource_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """Soft-delete a server resource (set is_active=False). Admin only."""
    result = await db.execute(
        select(ServerResource).where(ServerResource.id == resource_id)
    )
    resource = result.scalar_one_or_none()
    if resource is None:
        raise NotFoundError("Server resource not found")

    resource.is_active = False
    await db.commit()


@router.post(
    "/{resource_id}/test-connection",
    response_model=ResourceTestConnectionResponse,
)
async def test_connection(
    resource_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """Test SSH connectivity to the server (ping-style). Admin only."""
    result = await db.execute(
        select(ServerResource).where(ServerResource.id == resource_id)
    )
    resource = result.scalar_one_or_none()
    if resource is None:
        raise NotFoundError("Server resource not found")
    if not resource.host or not resource.ssh_username or not resource.ssh_private_key:
        return ResourceTestConnectionResponse(
            ok=False,
            message="Server has no host, SSH username, or private key configured.",
        )
    result = await asyncio.to_thread(
        run_command,
        resource.host,
        "echo ok",
        port=resource.ssh_port,
        username=resource.ssh_username,
        private_key=resource.ssh_private_key,
        timeout_sec=10.0,
    )
    return ResourceTestConnectionResponse(
        ok=result.ok,
        message=result.message,
        stdout=result.stdout or None,
        stderr=result.stderr or None,
    )
