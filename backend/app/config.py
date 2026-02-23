import os
from functools import lru_cache

from pydantic import Field, computed_field, model_validator
from pydantic_settings import BaseSettings

# backend 루트 (local: .../backend, Docker: /app)
_APP_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.dirname(_APP_DIR)


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "GPU Server Reservation System"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/server_reservation"
    )

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
    def resolve_paths(self):
        path = (self.GOOGLE_SERVICE_ACCOUNT_FILE or "").strip()
        if path and not os.path.isabs(path):
            self.GOOGLE_SERVICE_ACCOUNT_FILE = os.path.normpath(
                os.path.join(BACKEND_ROOT, path)
            )
        path = (self.LOG_ERROR_FILE or "").strip()
        if path and not os.path.isabs(path):
            self.LOG_ERROR_FILE = os.path.normpath(
                os.path.join(BACKEND_ROOT, path)
            )
        return self

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # Reservation policy (예약 최대 허용 시간, 시간 단위)
    MAX_RESERVATION_HOURS: int = 24 * 7  # 168 hours (7 days)

    # 서버 계정 예외: 예약 선택 목록에서 항상 제외할 OS 계정 (수정/삭제 불가, 시스템 기본값)
    # 환경변수 EXCLUDE_USERS="root,dev,admin" 처럼 쉼표 구분 문자열 (빈 값이면 기본값 사용)
    exclude_users_raw: str = Field(
        default="root,dev,admin,teleport,ubuntu",
        validation_alias="EXCLUDE_USERS",
    )

    @computed_field
    @property
    def EXCLUDE_USERS(self) -> list[str]:
        raw = (self.exclude_users_raw or "").strip()
        if not raw:
            return ["root", "dev", "admin", "teleport", "ubuntu"]
        return [x.strip() for x in raw.split(",") if x.strip()]

    # 최초 관리자 시드 (설정 시 앱 기동 시 admin 0명이면 이 계정으로 생성)
    ADMIN_EMAIL: str = ""
    ADMIN_PASSWORD: str = ""

    # 예약 이벤트 프로세스 (세션 스케줄러): WAS 서버에서는 true, 로컬 개발에서는 false 권장
    RESERVATION_EVENT_PROCESS_ENABLED: str = "false"

    # 에러 로그 파일 (빈 문자열이면 파일 미사용, 콘솔만). 상대 경로 시 backend 루트 기준
    LOG_ERROR_FILE: str = "logs/error.log"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


@lru_cache
def get_settings() -> Settings:
    return Settings()
