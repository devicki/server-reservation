import os

from pydantic_settings import BaseSettings
from pydantic import model_validator
from functools import lru_cache

# backend 루트 (local: .../backend, Docker: /app)
_APP_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.dirname(_APP_DIR)


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "GPU Server Reservation System"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/server_reservation"

    # JWT
    JWT_SECRET_KEY: str = "change-me-in-production-use-a-long-random-string"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Google Calendar (상대 경로 시 backend 루트 기준으로 해석, Docker·local 공유 가능)
    GOOGLE_SERVICE_ACCOUNT_FILE: str = ""
    GOOGLE_CALENDAR_ID: str = ""
    GOOGLE_CALENDAR_ENABLED: bool = False

    @model_validator(mode="after")
    def resolve_google_service_account_path(self):
        path = (self.GOOGLE_SERVICE_ACCOUNT_FILE or "").strip()
        if path and not os.path.isabs(path):
            self.GOOGLE_SERVICE_ACCOUNT_FILE = os.path.normpath(
                os.path.join(BACKEND_ROOT, path)
            )
        return self

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


@lru_cache
def get_settings() -> Settings:
    return Settings()
