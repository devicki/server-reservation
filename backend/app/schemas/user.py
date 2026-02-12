from pydantic import BaseModel

from app.models.user import UserRole
from app.schemas.auth import UserResponse


class UserListResponse(BaseModel):
    items: list[UserResponse]
    total: int


class UserUpdateRequest(BaseModel):
    role: UserRole | None = None
    is_active: bool | None = None
