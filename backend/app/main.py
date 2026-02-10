import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.api.v1.auth import router as auth_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.reservations import router as reservations_router
from app.api.v1.resources import router as resources_router
from app.config import get_settings
from app.database import async_session_factory
from app.models.server_resource import ServerResource

settings = get_settings()

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    if settings.GOOGLE_CALENDAR_ENABLED:
        if settings.GOOGLE_SERVICE_ACCOUNT_FILE:
            logger.info("Google Calendar: enabled, key file=%s", settings.GOOGLE_SERVICE_ACCOUNT_FILE)
        else:
            logger.warning("Google Calendar: enabled but GOOGLE_SERVICE_ACCOUNT_FILE not set")
    else:
        logger.info("Google Calendar: disabled")
    await seed_default_server_resource()
    yield
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
app.include_router(resources_router, prefix=API_V1_PREFIX)
app.include_router(reservations_router, prefix=API_V1_PREFIX)
app.include_router(dashboard_router, prefix=API_V1_PREFIX)


@app.get("/health")
async def health_check():
    return {"status": "ok", "version": settings.APP_VERSION}
