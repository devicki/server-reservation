import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class FeedbackCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class FeedbackCommentCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=1000)


class FeedbackCommentResponse(BaseModel):
    id: uuid.UUID
    feedback_id: uuid.UUID
    user_id: uuid.UUID
    user_name: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class FeedbackReactionSummary(BaseModel):
    like: int = 0


class FeedbackResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    user_name: str
    content: str
    created_at: datetime
    comment_count: int = 0
    comments: list[FeedbackCommentResponse] = []
    reaction_counts: FeedbackReactionSummary = Field(default_factory=FeedbackReactionSummary)
    user_reaction: str | None = None  # "like" or None

    model_config = {"from_attributes": True}


class FeedbackListResponse(BaseModel):
    items: list[FeedbackResponse]
    total: int
