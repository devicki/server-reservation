"""Serve case schemas — Local LLM serve 사례 공유 요청/응답."""
import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ServeCaseCreateRequest(BaseModel):
    server_resource_id: uuid.UUID
    model_name: str = Field(min_length=1, max_length=200)
    model_info: str | None = Field(None, max_length=4000)
    serve_command: str = Field(min_length=1, max_length=8000)
    resource_allocation: str | None = Field(None, max_length=2000)
    notes: str | None = Field(None, max_length=2000)


class ServeCaseResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    user_name: str
    server_resource_id: uuid.UUID
    server_name: str
    model_name: str
    model_info: str | None
    serve_command: str
    resource_allocation: str | None
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ServeCaseListResponse(BaseModel):
    items: list[ServeCaseResponse]
    total: int
