import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ResourceCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    capacity: int | None = Field(default=None, ge=1)


class ResourceUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    capacity: int | None = Field(default=None, ge=1)
    is_active: bool | None = None


class ResourceResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    capacity: int | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ResourceListResponse(BaseModel):
    items: list[ResourceResponse]
    total: int
