from fastapi import APIRouter

from app.config import get_settings

router = APIRouter(prefix="/config", tags=["Config"])


@router.get("")
async def get_public_config():
    """Public config for frontend (e.g. reservation policy, default exclude users). No auth required."""
    settings = get_settings()
    return {
        "max_reservation_hours": settings.MAX_RESERVATION_HOURS,
        "default_exclude_users": list(settings.EXCLUDE_USERS),
    }
