import logging
from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.api.v1.auth import router as auth_router
from app.api.v1.config import router as config_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.feedback import router as feedback_router
from app.api.v1.reservations import router as reservations_router
from app.api.v1.resources import router as resources_router
from app.api.v1.session_logs import router as session_logs_router
from app.api.v1.users import router as users_router
from app.config import get_settings
from app.core.security import hash_password
from app.database import async_session_factory
from app.models.server_resource import ServerResource
from app.models.user import User, UserRole
from app.services.session_scheduler import SessionScheduler

settings = get_settings()

# 로그 타임스탬프를 한국 시간(KST)으로 표시
KST = ZoneInfo("Asia/Seoul")


class KSTFormatter(logging.Formatter):
    def converter(self, timestamp):
        return datetime.fromtimestamp(timestamp, tz=KST).timetuple()

    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=KST)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.strftime("%Y-%m-%d %H:%M:%S")


logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
# basicConfig로 만든 핸들러에 KST 포매터 적용
_log_fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
_date_fmt = "%Y-%m-%d %H:%M:%S"
for h in logging.root.handlers:
    h.setFormatter(KSTFormatter(_log_fmt, _date_fmt))
logger = logging.getLogger(__name__)

# Scheduler instance (global)
scheduler = AsyncIOScheduler()


async def seed_default_server_resource():
    """서버 자원이 하나도 없으면 기본 자원 1개 생성 (Server Status에 표시되도록)."""
    async with async_session_factory() as session:
        try:
            result = await session.execute(select(ServerResource).limit(1))
            if result.scalar_one_or_none() is not None:
                return
            resource = ServerResource(
                name="GPU Server A",
                description="Default GPU server for reservation",
                is_active=True,
            )
            session.add(resource)
            await session.commit()
            logger.info("Seeded default server resource: GPU Server A")
        except Exception as e:
            logger.warning("Seed default server resource skipped: %s", e)
            await session.rollback()


async def seed_initial_admin():
    """관리자가 0명이고 ADMIN_EMAIL/ADMIN_PASSWORD가 설정돼 있으면 최초 관리자 1명 생성."""
    if not (settings.ADMIN_EMAIL and settings.ADMIN_PASSWORD):
        return
    async with async_session_factory() as session:
        try:
            result = await session.execute(
                select(User).where(User.role == UserRole.ADMIN).limit(1)
            )
            if result.scalar_one_or_none() is not None:
                return
            admin = User(
                email=settings.ADMIN_EMAIL.strip(),
                password_hash=hash_password(settings.ADMIN_PASSWORD),
                name="Admin",
                role=UserRole.ADMIN,
                is_active=True,
            )
            session.add(admin)
            await session.commit()
            logger.info("Seeded initial admin: %s", settings.ADMIN_EMAIL)
        except Exception as e:
            logger.warning("Seed initial admin skipped: %s", e)
            await session.rollback()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    if settings.GOOGLE_CALENDAR_ENABLED:
        if settings.GOOGLE_SERVICE_ACCOUNT_FILE:
            logger.info(
                "Google Calendar: enabled, key file=%s",
                settings.GOOGLE_SERVICE_ACCOUNT_FILE,
            )
        else:
            logger.warning(
                "Google Calendar: enabled but GOOGLE_SERVICE_ACCOUNT_FILE not set"
            )
    else:
        logger.info("Google Calendar: disabled")
    await seed_default_server_resource()
    await seed_initial_admin()

    # 예약 이벤트 프로세스(세션 스케줄러): 환경변수로 켜기/끄기 (WAS: True, 로컬 개발: False)
    if settings.RESERVATION_EVENT_PROCESS_ENABLED.lower() == "true":
        logger.info("Starting session scheduler (interval: 1 minute)")
        scheduler.add_job(
            SessionScheduler.process_reservation_events,
            "interval",
            minutes=1,
            id="reservation_session_processor",
            replace_existing=True,
            max_instances=1,  # Prevent concurrent execution
        )
        scheduler.start()
        logger.info("Session scheduler started successfully")
    else:
        logger.info(
            "Session scheduler disabled (RESERVATION_EVENT_PROCESS_ENABLED=false)"
        )

    yield

    # Shutdown scheduler (기동했을 때만 의미 있음)
    if settings.RESERVATION_EVENT_PROCESS_ENABLED.lower() == "true":
        logger.info("Shutting down session scheduler...")
        scheduler.shutdown(wait=True)
    logger.info("Shutting down...")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API v1 routers
API_V1_PREFIX = "/api/v1"
app.include_router(auth_router, prefix=API_V1_PREFIX)
app.include_router(config_router, prefix=API_V1_PREFIX)
app.include_router(resources_router, prefix=API_V1_PREFIX)
app.include_router(users_router, prefix=API_V1_PREFIX)
app.include_router(reservations_router, prefix=API_V1_PREFIX)
app.include_router(dashboard_router, prefix=API_V1_PREFIX)
app.include_router(feedback_router, prefix=API_V1_PREFIX)
app.include_router(session_logs_router, prefix=API_V1_PREFIX)


@app.get("/health")
async def health_check():
    return {"status": "ok", "version": settings.APP_VERSION}
