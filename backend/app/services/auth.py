import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, UnauthorizedError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User


class AuthService:
    @staticmethod
    async def register(
        db: AsyncSession, email: str, password: str, name: str
    ) -> User:
        """Register a new user."""
        # Check if email already exists
        result = await db.execute(select(User).where(User.email == email))
        if result.scalar_one_or_none():
            raise BadRequestError("Email already registered")

        user = User(
            email=email,
            password_hash=hash_password(password),
            name=name,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    @staticmethod
    async def login(
        db: AsyncSession, email: str, password: str
    ) -> dict:
        """Authenticate user and return tokens."""
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if user is None or not verify_password(password, user.password_hash):
            raise UnauthorizedError("Invalid email or password")

        if not user.is_active:
            raise UnauthorizedError("Account is inactive")

        from app.config import get_settings
        settings = get_settings()

        return {
            "access_token": create_access_token(user.id, user.role.value),
            "refresh_token": create_refresh_token(user.id),
            "token_type": "bearer",
            "expires_in": settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        }

    @staticmethod
    async def refresh_token(db: AsyncSession, refresh_token: str) -> dict:
        """Refresh access token using refresh token."""
        try:
            payload = decode_token(refresh_token)
            if payload.get("type") != "refresh":
                raise UnauthorizedError("Invalid token type")
            user_id = uuid.UUID(payload["sub"])
        except Exception:
            raise UnauthorizedError("Invalid or expired refresh token")

        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if user is None or not user.is_active:
            raise UnauthorizedError("User not found or inactive")

        from app.config import get_settings
        settings = get_settings()

        return {
            "access_token": create_access_token(user.id, user.role.value),
            "refresh_token": create_refresh_token(user.id),
            "token_type": "bearer",
            "expires_in": settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        }
