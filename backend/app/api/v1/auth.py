from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.auth import (
    RefreshTokenRequest,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(body: UserRegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user account."""
    user = await AuthService.register(
        db=db, email=body.email, password=body.password, name=body.name
    )
    return user


@router.post("/login", response_model=TokenResponse)
async def login(body: UserLoginRequest, db: AsyncSession = Depends(get_db)):
    """Login and receive JWT tokens."""
    return await AuthService.login(db=db, email=body.email, password=body.password)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    body: RefreshTokenRequest, db: AsyncSession = Depends(get_db)
):
    """Refresh the access token using a refresh token."""
    return await AuthService.refresh_token(db=db, refresh_token=body.refresh_token)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get the current authenticated user's profile."""
    return current_user
