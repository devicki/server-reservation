import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class FeedbackCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class FeedbackResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    user_name: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class FeedbackListResponse(BaseModel):
    items: list[FeedbackResponse]
    total: int
