from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1 import api_router
from app.bootstrap import init_db
from app.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import get_logger, setup_logging

settings = get_settings()
logger = get_logger(__name__)
STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    logger.info("Starting %s (%s)", settings.app_name, settings.app_env)
    await init_db()
    yield
    logger.info("Shutting down %s", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    description=(
        "Scalable API Aggregation Platform. Proxies and normalizes live responses "
        "from multiple third-party providers (e.g. airlines) into a single REST API. "
        "Does not store search or booking data."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

register_exception_handlers(app)
app.include_router(api_router, prefix=settings.api_v1_prefix)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/health", tags=["System"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


@app.get("/admin", tags=["Admin UI"], include_in_schema=False)
async def admin_panel() -> FileResponse:
    return FileResponse(STATIC_DIR / "admin.html")
