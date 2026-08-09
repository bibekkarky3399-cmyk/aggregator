from fastapi import APIRouter

from app.api.v1.admin_metrics import router as admin_metrics_router
from app.api.v1.admin_providers import router as admin_providers_router
from app.api.v1.aggregate import router as aggregate_router
from app.api.v1.auth import router as auth_router
from app.api.v1.booking import router as booking_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(admin_providers_router)
api_router.include_router(admin_metrics_router)
api_router.include_router(aggregate_router)
api_router.include_router(booking_router)
