import asyncio
import re
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_current_user
from app.config import get_settings
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.server_resource import ServerResource
from app.models.user import User, UserRole
from app.schemas.resource import (
    ResourceCreateRequest,
    ResourceListResponse,
    ResourcePermissionCheckResponse,
    ResourceResponse,
    ResourceTestConnectionResponse,
    ResourceUpdateRequest,
    RemoteUsersResponse,
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
        account_exclusions=body.account_exclusions,
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
    if body.account_exclusions is not None:
        resource.account_exclusions = body.account_exclusions

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


# Nonexistent username used only to test usermod permission (no real user affected).
_USERMOD_TEST_USER = "__permcheck_nonexistent_xyz__"


def _parse_permission_check(stdout: str, stderr: str) -> tuple[bool, bool]:
    """Parse output of sudo -n usermod -L and sudo -n pkill.
    usermod: Permission denied / cannot lock / password / not in sudoers (in usermod section only) → no permission.
    'does not exist' or 'unknown user' in usermod section → we have permission.
    pkill: in pkill section only, password / not in sudoers → no permission; pkill_exit:0 → permission ok.
    Split by line containing 'usermod_exit:' so output before it = usermod section, after = pkill section.
    """
    combined = ((stdout or "") + "\n" + (stderr or "")).lower()
    lines = combined.splitlines()
    usermod_end = -1
    for i, line in enumerate(lines):
        if re.search(r"usermod_exit:\d+", line):
            usermod_end = i
            break
    if usermod_end >= 0:
        usermod_section = "\n".join(lines[: usermod_end + 1])
        pkill_section = "\n".join(lines[usermod_end + 1 :])
    else:
        usermod_section = combined
        pkill_section = ""

    usermod_denied = (
        "permission denied" in usermod_section
        or "cannot lock" in usermod_section
        or "password" in usermod_section
        or "not in sudoers" in usermod_section
        or ("sudo:" in usermod_section and "is not in the sudoers" in usermod_section)
    )
    usermod_ok = (
        not usermod_denied
        and (
            "does not exist" in usermod_section
            or "unknown user" in usermod_section
            or bool(re.search(r"usermod_exit:0\b", usermod_section))
            or bool(re.search(r"usermod_exit:6\b", usermod_section))
        )
    )

    pkill_denied = (
        "password" in pkill_section
        or "not in sudoers" in pkill_section
        or ("sudo:" in pkill_section and "is not in the sudoers" in pkill_section)
    )
    pkill_ok = not pkill_denied and bool(re.search(r"pkill_exit:0\b", pkill_section))
    return usermod_ok, pkill_ok


@router.post(
    "/{resource_id}/check-permissions",
    response_model=ResourcePermissionCheckResponse,
)
async def check_permissions(
    resource_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """Check if the SSH user can run sudo usermod / sudo pkill (other-user deactivate and process kill). Admin only.
    Uses sudo -n (non-interactive). sudoers에 해당 계정이 usermod/pkill 권한으로 등록돼 있어야 함.
    """
    result = await db.execute(
        select(ServerResource).where(ServerResource.id == resource_id)
    )
    resource = result.scalar_one_or_none()
    if resource is None:
        raise NotFoundError("Server resource not found")
    if not resource.host or not resource.ssh_username or not resource.ssh_private_key:
        return ResourcePermissionCheckResponse(
            ok=False,
            message="Server has no host, SSH username, or private key configured.",
            usermod_ok=False,
            pkill_ok=False,
        )
    # 다른 사용자 비활성화/프로세스 종료 권한: sudo로 실행 가능한지 확인 (sudo -n = 비밀번호 없이).
    # usermod -L: 존재하지 않는 사용자에 대해 잠금 시도 → 권한 있으면 "does not exist", 없으면 Permission denied/cannot lock/sudo 거부.
    usermod_cmd = f"sudo -n usermod -L {_USERMOD_TEST_USER} 2>&1; echo usermod_exit:$?"
    pkill_cmd = "sudo -n pkill -h 2>&1; echo pkill_exit:$?"
    cmd = f"({usermod_cmd}); ({pkill_cmd})"
    run_result = await asyncio.to_thread(
        run_command,
        resource.host,
        cmd,
        port=resource.ssh_port,
        username=resource.ssh_username,
        private_key=resource.ssh_private_key,
        timeout_sec=15.0,
    )
    if not run_result.ok:
        return ResourcePermissionCheckResponse(
            ok=False,
            message=run_result.message,
            usermod_ok=False,
            pkill_ok=False,
        )
    usermod_ok, pkill_ok = _parse_permission_check(
        run_result.stdout or "", run_result.stderr or ""
    )
    return ResourcePermissionCheckResponse(
        ok=True,
        message=None,
        usermod_ok=usermod_ok,
        pkill_ok=pkill_ok,
    )


def _parse_getent_passwd_home(stdout: str) -> list[str]:
    """Parse getent passwd | grep '/home' output; return list of usernames (first column)."""
    usernames: list[str] = []
    for line in stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(":")
        if len(parts) >= 6 and "/home" in parts[5]:
            name = parts[0].strip()
            if name and name not in usernames:
                usernames.append(name)
    return sorted(usernames)


def _parse_exclusions(raw: str | None) -> set[str]:
    """Parse account_exclusions string (comma or newline separated) into set of usernames."""
    if not raw or not raw.strip():
        return set()
    out: set[str] = set()
    for part in raw.replace(",", "\n").splitlines():
        name = part.strip()
        if name:
            out.add(name)
    return out


@router.get("/{resource_id}/remote-users", response_model=RemoteUsersResponse)
async def get_remote_users(
    resource_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """Get OS user list from the server (getent passwd | grep '/home'). Requires resource to have SSH configured."""
    result = await db.execute(
        select(ServerResource).where(ServerResource.id == resource_id)
    )
    resource = result.scalar_one_or_none()
    if resource is None:
        raise NotFoundError("Server resource not found")
    if not resource.host or not resource.ssh_username or not resource.ssh_private_key:
        return RemoteUsersResponse(items=[])
    run_result = await asyncio.to_thread(
        run_command,
        resource.host,
        "getent passwd | grep '/home'",
        port=resource.ssh_port,
        username=resource.ssh_username,
        private_key=resource.ssh_private_key,
        timeout_sec=15.0,
    )
    if not run_result.ok:
        return RemoteUsersResponse(items=[])
    usernames = _parse_getent_passwd_home(run_result.stdout)
    default_exclude = set(get_settings().EXCLUDE_USERS)
    server_exclude = _parse_exclusions(resource.account_exclusions)
    exclusions = default_exclude | server_exclude
    usernames = [u for u in usernames if u not in exclusions]
    return RemoteUsersResponse(
        items=[{"username": u} for u in usernames]
    )
