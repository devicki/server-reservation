import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ResourceCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    capacity: int | None = Field(default=None, ge=1)
    host: str | None = Field(default=None, max_length=255)
    ssh_port: int = Field(default=22, ge=1, le=65535)
    ssh_username: str | None = Field(default=None, max_length=100)
    ssh_private_key: str | None = None
    account_exclusions: str | None = None


class ResourceUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    capacity: int | None = Field(default=None, ge=1)
    is_active: bool | None = None
    host: str | None = Field(default=None, max_length=255)
    ssh_port: int | None = Field(default=None, ge=1, le=65535)
    ssh_username: str | None = Field(default=None, max_length=100)
    ssh_private_key: str | None = None
    account_exclusions: str | None = None


class ResourceResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    capacity: int | None
    is_active: bool
    host: str | None = None
    ssh_port: int = 22
    ssh_username: str | None = None
    ssh_private_key: str | None = None
    account_exclusions: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ResourceListResponse(BaseModel):
    items: list[ResourceResponse]
    total: int


class ResourceTestConnectionResponse(BaseModel):
    ok: bool
    message: str
    stdout: str | None = None
    stderr: str | None = None


class ResourcePermissionCheckResponse(BaseModel):
    """SSH 사용자의 usermod, pkill, teleport 실행 권한 확인 결과."""

    ok: bool
    message: str | None = None
    usermod_ok: bool = False
    pkill_ok: bool = False
    teleport_ok: bool = False


class RemoteUserItem(BaseModel):
    username: str


class RemoteUsersResponse(BaseModel):
    items: list[RemoteUserItem]
